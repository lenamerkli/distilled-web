from jinja2 import Template, TemplateError
from json import load, dump, loads, JSONDecodeError
from os import listdir, environ
from os.path import getsize, exists
from requests import request, RequestException
from subprocess import Popen, PIPE, run
from threading import Lock
from datetime import datetime
from dotenv import load_dotenv
import typing as t
import socket
import sys


load_dotenv()


DEFAULT_SEED = 65536

REPETITION_CHECK_SPAN = 10000     # how far back to search (chars)
# (window_size, min_occurrences) — shorter windows need more hits
REPETITION_RULES = [
    (30, 30),
    (50, 25),
    (80, 15),
    (150, 12),
    (300, 6),
    (1000, 4),
]


if not exists('/opt/llms/index.json'):
    with open('/opt/llms/index.json', 'w') as _f:
        dump({}, _f)
with open('/opt/llms/index.json') as _f:
    LOCAL_MODELS = load(_f)


def strftime_now(format_):
    return datetime.now().strftime(format_)


def raise_exception(message):
    raise TemplateError(message)


class ModelResponse:
    def __init__(self, model: str, response: str, thinking: str = '', input_tokens: int = 0, output_tokens: int = 0):
        self.model = model
        self.response = response
        self.thinking = thinking
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class BaseLLM:

    def __init__(self):
        self._stored_temperature = None
        self._stored_top_k = None
        self._stored_top_p = None
        self._stored_min_p = None
        self._stored_enable_thinking = None
        self._stored_n_predict = None
        self._stored_grammar = None
        self._stored_seed = None

    def set_model(self, model_name: str) -> None:
        raise NotImplementedError

    def get_model(self) -> str:
        raise NotImplementedError

    def load_model(self) -> None:
        raise NotImplementedError

    def is_loading(self) -> bool:
        raise False

    def is_running(self) -> bool:
        raise True

    def stop(self) -> None:
        pass

    def _resolve_enable_thinking(self, enable_thinking: t.Optional[bool]) -> bool:
        """Resolve the effective enable_thinking value.
        Priority: explicit call-site value > stored from load_model > True.
        """
        if enable_thinking is not None:
            return enable_thinking
        if self._stored_enable_thinking is not None:
            return self._stored_enable_thinking
        return True

    def _resolve_temperature(self, temperature: t.Optional[float]) -> t.Optional[float]:
        if temperature is not None:
            return temperature
        return self._stored_temperature

    def _resolve_top_k(self, top_k: t.Optional[int]) -> t.Optional[int]:
        if top_k is not None:
            return top_k
        return self._stored_top_k

    def _resolve_top_p(self, top_p: t.Optional[float]) -> t.Optional[float]:
        if top_p is not None:
            return top_p
        return self._stored_top_p

    def _resolve_min_p(self, min_p: t.Optional[float]) -> t.Optional[float]:
        if min_p is not None:
            return min_p
        return self._stored_min_p

    def generate(
            self,
            prompt: t.Union[str, t.List[t.Dict[str, str]]],
            enable_thinking: bool = True,
            temperature: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            top_p: t.Optional[float] = None,
            min_p: t.Optional[float] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            seed: t.Optional[int] = None
    ) -> ModelResponse:
        raise NotImplementedError


class LLaMaCPP(BaseLLM):

    def __init__(self):
        """
        Initialize a new instance of LLaMaCPP
        """
        super().__init__()
        self._model_name = None
        self._process = None
        self._readers = 0
        self._read_lock = Lock()
        self._write_lock = Lock()
        self._port = 8432

    def _add_reader(self):
        with self._read_lock:
            self._readers += 1
            if self._readers == 1:
                self._write_lock.acquire()

    def _remove_reader(self):
        with self._read_lock:
            self._readers -= 1
            if self._readers == 0:
                self._write_lock.release()

    @staticmethod
    def min_none(a: t.Any, b: t.Any) -> t.Any:
        """
        Returns the minimum of two values, or the single value if one of them is None.

        :param a: First value
        :param b: Second value
        :return: The minimum of a and b, or a/b if one of them is None
        """
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    def calculate_offload_layers(self, model_name: str, short_model_name: str) -> int:
        """
        Calculates the number of layers to offload

        :param model_name: The name of the model
        :param short_model_name: The short name of the model
        :return: The number of layers to offload
        """
        free_vram = self.check_free_vram() - 256
        llm_size = getsize(f"/opt/llms/{model_name}") / (1024 ** 2)  # from bytes to MiB
        llm_size = llm_size * 1.1  # Adjust for fluctuation
        layers = LOCAL_MODELS[short_model_name]['layers']
        vram_per_layer = llm_size / layers
        return min(int(free_vram / vram_per_layer), layers)

    @staticmethod
    def check_free_vram() -> int:
        """
        Checks the amount of free VRAM on the GPU

        :return: The amount of free VRAM in MiB
        :raises Exception: If `nvidia-smi` fails
        """
        nvidia_smi = run([
            'nvidia-smi',
            '--query-gpu=memory.free',
            '--format=csv,nounits,noheader'
        ], stdout=PIPE, text=True)
        if nvidia_smi.returncode != 0:
            raise Exception(nvidia_smi.stderr)
        return int(nvidia_smi.stdout)

    def set_model(self, model_name: str) -> None:
        """
        Sets the model to use

        :param model_name: The file name of the model to use, including the `.gguf` extension
        :return: None
        :raises Exception: If the model is not found
        """
        if model_name not in self.list_available_models():
            raise Exception(f"Model {model_name} not found")
        with self._write_lock:
            self._model_name = model_name

    def get_model(self) -> str:
        return self._model_name

    def load_model(
            self,
            print_log: bool = False,
            seed: t.Optional[int] = None,
            threads: t.Optional[int] = None,
            kv_cache_type: t.Optional[t.Literal['f16', 'bf16', 'q8_0', 'q5_0', 'q4_0']] = None,
            context: t.Optional[int] = None,
            temperature: t.Optional[float] = None,
            top_p: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            min_p: t.Optional[float] = None,
            enable_thinking: t.Optional[bool] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            cpu_only: bool = False,
    ) -> None:
        """
        Load the selected model into memory

        :param print_log: Whether to print the stdout from llama.cpp into the stdout
        :param seed: Random seed for reproducible outputs
        :param threads: The number of threads to use (default: 16)
        :param kv_cache_type: The type of key-value cache to use (default: q8_0)
        :param context: The maximum context size to allocate (depends on the model's default)
        :param temperature: Controls randomness in generation. Higher values (e.g., 0.8) make output more random, lower values (e.g., 0.2) make it more deterministic
        :param top_k: Limits sampling to the k most likely tokens at each step. If set to 0 or None, no limit is applied
        :param top_p: Nucleus sampling - only considers tokens whose cumulative probability exceeds the probability threshold p
        :param min_p: Minimum probability threshold for token sampling - excludes tokens below this probability
        :param enable_thinking: Whether to enable the model's thinking mode, if supported by the model
        :param n_predict: Maximum number of tokens to predict/generate
        :param grammar: Optional grammar constraints for structured generation
        :param cpu_only: Use CPU-only mode
        :return: None
        :raises Exception: If a model is already loaded, the model name is not set, or the model is not found
        """
        if self.process_is_alive():
            raise Exception("A model is already loaded. Use stop() before loading a new model.")
        if self._model_name is None:
            raise Exception("Model not set")
        short_name = self.short_model_name(self._model_name)
        if short_name is None:
            raise Exception(f"Model {self._model_name} not found")
        if seed is None:
            seed = -1
        if threads is None:
            threads = 16
        if kv_cache_type is None:
            kv_cache_type = 'q8_0'
        if cpu_only:
            kv_cache_type = 'f16'
        context = self.min_none(context, LOCAL_MODELS[short_name]['context'])
        short_info = LOCAL_MODELS[short_name]
        has_sampling = 'sampling' in short_info
        has_sampling_thinking = 'sampling_thinking' in short_info
        if enable_thinking:
            index = 'sampling_thinking' if has_sampling_thinking else 'sampling'
        elif enable_thinking is False:
            index = 'sampling' if has_sampling else 'sampling_thinking'
        else:
            index = 'sampling' if has_sampling else 'sampling_thinking'
        if temperature is None:
            temperature = short_info[index]['temperature']
        if top_p is None:
            top_p = short_info[index]['top_p']
        if top_k is None:
            top_k = short_info[index]['top_k']
        if min_p is None:
            min_p = short_info[index]['min_p']

        # Store parameters for use in generate() when not overridden
        self._stored_temperature = temperature
        self._stored_top_k = top_k
        self._stored_top_p = top_p
        self._stored_min_p = min_p
        self._stored_enable_thinking = enable_thinking
        self._stored_n_predict = n_predict
        self._stored_grammar = grammar
        self._stored_seed = seed

        while is_port_in_use(self._port):
            self._port += 1
        with self._write_lock:
            if not cpu_only:
                offload_layers = self.calculate_offload_layers(self._model_name, short_name)
            else:
                offload_layers = 0
            print(f"Loading model {self._model_name} with {offload_layers} layers offloaded")
            command = [
                '/opt/llama.cpp/bin/llama-server',
                '--threads', str(threads),
                '--ctx-size', str(context),
                '--no-escape',
                '--cache-type-k', kv_cache_type,
                '--cache-type-v', kv_cache_type,
                '--mlock',
                '--n-gpu-layers', str(offload_layers),
                '--model', f'/opt/llms/{self._model_name}',
                '--seed', str(seed),
                '--temp', str(temperature),
                '--top-k', str(top_k),
                '--top-p', str(top_p),
                '--min-p', str(min_p),
                '--host', '127.0.0.1',
                '--port', str(self._port),
                '--alias', short_name,
                '--slots',
                '--metrics',
            ]
            if print_log:
                stdout = None
                stderr = None
                print(command)
            else:
                stdout = PIPE
                stderr = PIPE
            self._process = Popen(command, stdout=stdout, stderr=stderr, text=True)
        return None

    def _resolve_effective_thinking(self, enable_thinking: bool) -> bool:
        """
        Resolve the effective enable_thinking value based on the model's capabilities.

        :param enable_thinking: The caller-requested enable_thinking value
        :return: The resolved (effective) enable_thinking value
        """
        short_name = self.short_model_name(self._model_name)
        if LOCAL_MODELS[short_name]['thinking']:
            if LOCAL_MODELS[short_name]['optional_thinking']:
                return enable_thinking
            return True
        return False

    def apply_chat_template(self, conversation: t.List[t.Dict[str, str]], enable_thinking: bool = True) -> str:
        """
        Applies the chat template to the conversation

        :param conversation: The conversation in ChatML format
        :param enable_thinking: Whether to enable thinking (only supported on certain models)
        :return: The conversation as a string
        """
        short_name = self.short_model_name(self._model_name)
        chat_template: str = LOCAL_MODELS[short_name]['chat_template']
        template = Template(chat_template)
        options: t.Dict[str, t.Any] = {
            'messages': conversation,
            'tools': [],
            'add_generation_prompt': True,
            'enable_thinking': self._resolve_effective_thinking(enable_thinking),
            'strftime_now': strftime_now,
            'raise_exception': raise_exception
        }
        return template.render(**options)

    def generate(
            self,
            prompt: t.Union[str, t.List[t.Dict[str, str]]],
            enable_thinking: t.Optional[bool] = None,
            temperature: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            top_p: t.Optional[float] = None,
            min_p: t.Optional[float] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            seed: t.Optional[int] = DEFAULT_SEED,
    ) -> ModelResponse:
        """
        Generate an answer or completion using the large language model based on the prompt

        :param prompt: Either a string containing the prompt text or a list of message dictionaries in ChatML format
        :param enable_thinking: Whether to enable the model's thinking mode, if supported by the model
        :param temperature: Controls randomness in generation. Higher values (e.g., 0.8) make output more random, lower values (e.g., 0.2) make it more deterministic
        :param top_k: Limits sampling to the k most likely tokens at each step. If set to 0 or None, no limit is applied
        :param top_p: Nucleus sampling - only considers tokens whose cumulative probability exceeds the probability threshold p
        :param min_p: Minimum probability threshold for token sampling - excludes tokens below this probability
        :param n_predict: Maximum number of tokens to predict/generate
        :param grammar: Optional grammar constraints for structured generation
        :param seed: Random seed for reproducible outputs
        :return: The generated ModelResponse from the model
        :raises Exception: If the model is not loaded or the request fails
        """
        resolved_enable_thinking = self._resolve_enable_thinking(enable_thinking)
        effective_thinking = self._resolve_effective_thinking(resolved_enable_thinking)
        resolved_temperature = self._resolve_temperature(temperature)
        resolved_top_k = self._resolve_top_k(top_k)
        resolved_top_p = self._resolve_top_p(top_p)
        resolved_min_p = self._resolve_min_p(min_p)
        resolved_n_predict = n_predict if n_predict is not None else self._stored_n_predict
        resolved_grammar = grammar if grammar is not None else self._stored_grammar
        resolved_seed = seed if seed is not None else self._stored_seed
        if isinstance(prompt, list):
            prompt = self.apply_chat_template(prompt, resolved_enable_thinking)
        json_data: t.Dict[str, t.Any] = {
            'prompt': prompt,
        }
        short_name = self.short_model_name(self._model_name)
        stop_tokens = LOCAL_MODELS[short_name].get('stop', [])
        if stop_tokens and isinstance(stop_tokens, list):
            json_data['stop'] = stop_tokens
        elif stop_tokens and isinstance(stop_tokens, str):
            json_data['stop'] = [stop_tokens]
        if resolved_temperature is not None:
            json_data['temperature'] = resolved_temperature
        if resolved_top_k is not None:
            json_data['top_k'] = resolved_top_k
        if resolved_top_p is not None:
            json_data['top_p'] = resolved_top_p
        if resolved_min_p is not None:
            json_data['min_p'] = resolved_min_p
        if resolved_n_predict is not None:
            json_data['n_predict'] = resolved_n_predict
        if resolved_grammar is not None:
            json_data['grammar'] = resolved_grammar
        if resolved_seed is not None:
            json_data['seed'] = resolved_seed
        self._add_reader()
        try:
            value = stream_passthrough_llama_cpp(
                json_data, self._port,
                original_prompt=json_data.get('prompt', ''),
            )
            if not value.response:
                raise Exception("Empty response from LLaMa.cpp")
            value.model = self._model_name
            return value
        finally:
            self._remove_reader()

    def process_is_alive(self) -> bool:
        """
        Checks if the process is still running

        :return: True if the process is running, False otherwise
        """
        self._add_reader()
        try:
            if self._process is None:
                return False
            return self._process.poll() is None
        finally:
            self._remove_reader()

    def is_loading(self) -> bool:
        """
        Checks if the model is loading

        :return: True if the model is loading, False otherwise
        """
        self._add_reader()
        try:
            req = request('GET', f"http://127.0.0.1:{self._port}/health")
            return req.status_code == 503
        except RequestException:
            return False
        finally:
            self._remove_reader()

    def is_running(self) -> bool:
        """
        Checks if the model is running

        :return: True if the model is running, False otherwise
        """
        self._add_reader()
        try:
            req = request('GET', f"http://127.0.0.1:{self._port}/health")
            return req.status_code == 200
        except RequestException:
            return False
        finally:
            self._remove_reader()

    def has_error(self) -> bool:
        """
        Checks if the model has an error

        :return: True if the model has an error, False otherwise
        """
        self._add_reader()
        try:
            req = request('GET', f"http://127.0.0.1:{self._port}/health")
            return req.status_code not in [200, 503]
        except RequestException:
            return True
        finally:
            self._remove_reader()

    def stop(self) -> None:
        """
        Stop the model
        """
        with self._write_lock:
            if self._process is None:
                return None
            self._process.terminate()
            return None

    def kill(self):
        """
        Kill the model using SIGKILL
        """
        with self._write_lock:
            if self._process is None:
                return None
            self._process.kill()
            return None

    def get_system_message(self) -> t.List[t.Dict[str, str]]:
        """
        Get the system message for the selected model

        :return: The system message in ChatML format
        """
        short_name = self.short_model_name(self._model_name)
        system_message = LOCAL_MODELS[short_name]['system_message']
        if system_message == '':
            return []
        return [{'role': 'system', 'content': system_message}]

    @staticmethod
    def list_available_models() -> t.List[str]:
        """
        List available models
        """
        directory_list = listdir('/opt/llms/')
        model_list = []
        for entry in directory_list:
            if entry.endswith('.gguf') and LLaMaCPP.short_model_name(entry) is not None:
                model_list.append(entry)
        return model_list

    @staticmethod
    def short_model_name(model_name: str) -> t.Optional[str]:
        """
        Extract the short model name from the long model file name

        :param model_name: The long model file name
        :return: The short model name (or None if not found)
        """
        for model in sorted(LOCAL_MODELS.keys(), key=lambda x: len(x), reverse=True):
            if model_name.startswith(model):
                return model
        return None


class OpenRouterLLM(BaseLLM):

    def __init__(self) -> None:
        """
        Initialize a new instance of OpenRouterLLM
        """
        super().__init__()
        self._model_name = ''

    def set_model(self, model_name: str) -> None:
        """
        Sets the model to use

        :param model_name: The name of the model to use
        """
        self._model_name = model_name

    def get_model(self) -> str:
        return self._model_name

    def load_model(
            self,
            temperature: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            top_p: t.Optional[float] = None,
            min_p: t.Optional[float] = None,
            enable_thinking: t.Optional[bool] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            seed: t.Optional[int] = None,
    ) -> None:
        self._stored_temperature = temperature
        self._stored_top_k = top_k
        self._stored_top_p = top_p
        self._stored_min_p = min_p
        self._stored_enable_thinking = enable_thinking
        self._stored_n_predict = n_predict
        self._stored_grammar = grammar
        self._stored_seed = seed

    def is_loading(self) -> bool:  # noqa
        return False

    def is_running(self) -> bool:  # noqa
        return True

    def apply_chat_template(self, conversation: t.List[t.Dict[str, str]], enable_thinking: bool = True) -> str:
        raise NotImplementedError

    def generate(
            self,
            prompt: t.Union[str, t.List[t.Dict[str, str]]],
            enable_thinking: t.Optional[bool] = None,
            temperature: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            top_p: t.Optional[float] = None,
            min_p: t.Optional[float] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            seed: t.Optional[int] = DEFAULT_SEED,
    ) -> ModelResponse:
        """
        Generate an answer or completion using the large language model based on the prompt

        :param prompt: Either a string containing the prompt text or a list of message dictionaries in ChatML format
        :param enable_thinking: Whether to enable the model's thinking mode, if supported by the model
        :param temperature: Controls randomness in generation. Higher values (e.g., 0.8) make output more random, lower values (e.g., 0.2) make it more deterministic
        :param top_k: (UNUSED) Limits sampling to the k most likely tokens at each step. If set to 0 or None, no limit is applied
        :param top_p: (UNUSED) Nucleus sampling - only considers tokens whose cumulative probability exceeds the probability threshold p
        :param min_p: (UNUSED) Minimum probability threshold for token sampling - excludes tokens below this probability
        :param n_predict: (UNUSED) Maximum number of tokens to predict/generate
        :param grammar: (UNUSED) Optional grammar constraints for structured generation
        :param seed: Random seed for reproducible outputs
        :return: The generated ModelResponse from the model
        :raises Exception: If the model is not loaded or the request fails
        """
        resolved_enable_thinking = self._resolve_enable_thinking(enable_thinking)
        resolved_temperature = self._resolve_temperature(temperature)
        if isinstance(prompt, str):
            data: t.Dict[str, t.Any] = {'prompt': prompt}
        else:
            data: t.Dict[str, t.Any] = {'messages': prompt}
        model_name = self._model_name.replace('OpenRouter', '').replace('openrouter', '')
        if model_name[0] == '/':
            model_name = model_name[1:]
        data['model'] = model_name
        if resolved_temperature is not None:
            data['temperature'] = resolved_temperature
        if seed is not None:
            data['seed'] = seed
        value = _stream_openai_compatible(
            json_data=data,
            url='https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + environ['OPENROUTER_API_KEY'],
            },
            verify='/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
        )
        if not value.response:
            raise Exception("Empty response from OpenRouter")
        value.model = self._model_name
        return value

    def stop(self) -> None:
        pass


class PublicAiLLM(BaseLLM):

    def __init__(self) -> None:
        """
        Initialize a new instance of PublicAiLLM
        """
        super().__init__()
        self._model_name = ''

    def set_model(self, model_name: str) -> None:
        """
        Sets the model to use

        :param model_name: The name of the model to use
        """
        self._model_name = model_name

    def get_model(self) -> str:
        return self._model_name

    def load_model(
            self,
            temperature: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            top_p: t.Optional[float] = None,
            min_p: t.Optional[float] = None,
            enable_thinking: t.Optional[bool] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            seed: t.Optional[int] = None,
    ) -> None:
        self._stored_temperature = temperature
        self._stored_top_k = top_k
        self._stored_top_p = top_p
        self._stored_min_p = min_p
        self._stored_enable_thinking = enable_thinking
        self._stored_n_predict = n_predict
        self._stored_grammar = grammar
        self._stored_seed = seed

    def is_loading(self) -> bool:  # noqa
        return False

    def is_running(self) -> bool:  # noqa
        return True

    def apply_chat_template(self, conversation: t.List[t.Dict[str, str]], enable_thinking: bool = True) -> str:
        raise NotImplementedError

    def generate(
            self,
            prompt: t.Union[str, t.List[t.Dict[str, str]]],
            enable_thinking: t.Optional[bool] = None,
            temperature: t.Optional[float] = None,
            top_k: t.Optional[int] = None,
            top_p: t.Optional[float] = None,
            min_p: t.Optional[float] = None,
            n_predict: t.Optional[int] = None,
            grammar: t.Optional[str] = None,
            seed: t.Optional[int] = DEFAULT_SEED,
    ) -> ModelResponse:
        """
        Generate an answer or completion using the large language model based on the prompt

        :param prompt: Either a string containing the prompt text or a list of message dictionaries in ChatML format
        :param enable_thinking: Whether to enable the model's thinking mode, if supported by the model
        :param temperature: (UNUSED) Controls randomness in generation. Higher values (e.g., 0.8) make output more random, lower values (e.g., 0.2) make it more deterministic
        :param top_k: (UNUSED) Limits sampling to the k most likely tokens at each step. If set to 0 or None, no limit is applied
        :param top_p: (UNUSED) Nucleus sampling - only considers tokens whose cumulative probability exceeds the probability threshold p
        :param min_p: (UNUSED) Minimum probability threshold for token sampling - excludes tokens below this probability
        :param n_predict: (UNUSED) Maximum number of tokens to predict/generate
        :param grammar: (UNUSED) Optional grammar constraints for structured generation
        :param seed: (UNUSED) Random seed for reproducible outputs
        :return: The generated ModelResponse from the model
        :raises Exception: If the model is not loaded or the request fails
        """
        resolved_enable_thinking = self._resolve_enable_thinking(enable_thinking)
        resolved_temperature = self._resolve_temperature(temperature)
        if isinstance(prompt, str):
            data: t.Dict[str, t.Any] = {'prompt': prompt}
        else:
            data: t.Dict[str, t.Any] = {'messages': prompt}
        model_name = self._model_name.replace('publicai', '')
        if model_name[0] == '/':
            model_name = model_name[1:]
        data['model'] = model_name
        if seed is not None:
            data['seed'] = seed
        value = _stream_openai_compatible(
            json_data=data,
            url='https://api.publicai.co/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + environ['PUBLICAI_API_KEY'],
                'User-Agent': 'LenaBench',
            },
            verify='/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
        )
        if not value.response:
            raise Exception("Empty response from PublicAI")
        value.model = self._model_name
        return value

    def stop(self) -> None:
        pass


def _find_repeating_window(text: str) -> tuple[int, str] | tuple[None, None]:
    """Find the earliest-position repeating window in the check region.

    Scans all window sizes defined in REPETITION_RULES across the tail
    portion of ``text``.  Returns the earliest character offset (relative
    to the start of the text) where any window begins, along with the
    matching window string, or ``(None, None)`` if nothing repeats.
    """
    if len(text) < 30:
        return None, None
    check_start = max(0, len(text) - REPETITION_CHECK_SPAN)
    check_region = text[check_start:]

    for window_size, min_occurrences in REPETITION_RULES:
        if len(check_region) < window_size * min_occurrences:
            continue
        seen: dict[str, int] = {}
        for i in range(len(check_region) - window_size + 1):
            window = check_region[i:i + window_size]
            count = seen.get(window, 0) + 1
            seen[window] = count
            if count >= min_occurrences:
                return check_start + i, window
    return None, None


def _detect_repetition(text: str) -> bool:
    """Return True if any window-size rule detects repetition."""
    found_pos, _ = _find_repeating_window(text)
    return found_pos is not None


def _force_close_response(response) -> None:
    """Force-close the underlying TCP connection of a streaming response.

    Python ``requests``' ``response.close()`` can block trying to drain
    the socket.  We bypass that by closing the raw urllib3 connection first,
    which sends a TCP RST so the llama.cpp server immediately sees the
    disconnection and cancels generation.
    """
    try:
        # Close the urllib3 HTTPResponse (the raw socket)
        response.raw.close()
    except Exception:
        pass
    try:
        response.close()
    except Exception:
        pass


def _count_tokens(port: int, text: str) -> int:
    """Count tokens in the given text using the llama.cpp /tokenize endpoint.

    Used during cutoff paths where the final ``timings`` event is never
    received, so ``prompt_n`` and ``predicted_n`` are unavailable.
    Returns 0 if the endpoint is unreachable.
    """
    try:
        resp = request(
            'POST',
            f"http://127.0.0.1:{port}/tokenize",
            json={'content': text, 'add_special': False},
        )
        if resp.status_code != 200:
            return 0
        return len(resp.json().get('tokens', []))
    except RequestException:
        return 0


def stream_passthrough_llama_cpp(
    json_data: dict,
    port: int,
    original_prompt: str,
) -> ModelResponse:
    """Stream a completion from llama.cpp, with repetition detection.

    Parameters
    ----------
    json_data : dict
        The JSON payload for ``POST /completion``.  ``stream`` is forced to
        ``True``.
    port : int
        Port the llama.cpp server is listening on.
    original_prompt : str or None
        The *original* prompt string (before any model output).  Required
        when a thinking-cutoff continuation is needed.

    Returns
    -------
    ModelResponse
    """
    json_data = dict(json_data)          # don't mutate the caller's dict
    json_data['stream'] = True
    url = f"http://127.0.0.1:{port}/completion"

    # ----------------------------------------------------------------
    # First attempt — stream with repetition detection
    # ----------------------------------------------------------------
    response = request('POST', url, json=json_data, stream=True)
    if response.status_code != 200:
        raise Exception(response.text)

    print(json_data['prompt'], end='\n', flush=True)

    full_content = ""
    input_tokens = 0
    output_tokens = 0
    total_output_tokens = 0
    thinking_cutoff = False
    response_cutoff = False
    token_count = 0          # fallback: count of SSE content events
    print('=' * 30 + ' BEGIN LLAMACPP STREAM ' + '=' * 30)
    for line in response.iter_lines():
        if not line:
            continue
        if line.startswith(b'data: '):
            try:
                event_data = loads(line[len('data: '):])
                token = event_data.get('content', '')
                full_content += token
                token_count += 1
                if token:
                    print(token, end='', flush=True)

                if event_data.get('stop', False):
                    timings = event_data.get('timings', {})
                    input_tokens = timings.get('prompt_n', 0)
                    output_tokens = timings.get('predicted_n', 0)
                    total_output_tokens += output_tokens
                    break

                # ---- Repetition detection ---------------------------
                if (('</think>' in full_content) or ('<channel|>' in full_content) or ('</think>' in original_prompt[-32:]) or ('<|channel>thought' in original_prompt[-32:])) or not (('<think>' in full_content) or ('<|channel>thought' in full_content) or ('<think>' in original_prompt[-32:]) or ('<|channel>thought' in original_prompt[-32:])):
                    # We are past the thinking tag → check response part
                    if '</think>' in full_content:
                        _, _, after_think = full_content.rpartition(
                            '</think>'
                        )
                    elif '<|channel>thought' in full_content:
                        _, _, after_think = full_content.rpartition(
                            '</channel>'
                        )
                    else:
                        after_think = full_content
                    if _detect_repetition(after_think):
                        print("\n==== RESPONSE CUTOFF DUE TO REPETITION ====\n")
                        print(f"{('</think>' in full_content)=}, {('<channel|>' in full_content)=}, {('<think>' in full_content)=}, {('<|channel>thought' in full_content)=}")
                        response_cutoff = True
                        _force_close_response(response)
                        break
                else:
                    # Still in the thinking phase
                    if _detect_repetition(full_content):
                        print("\n==== THINKING CUTOFF DUE TO REPETITION ====\n")
                        thinking_cutoff = True
                        _force_close_response(response)
                        break

            except JSONDecodeError:
                print(f"[ERROR] Invalid JSON: {line}", file=sys.stderr)

    # ----------------------------------------------------------------
    # Normal completion (no cutoff)
    # ----------------------------------------------------------------
    if not thinking_cutoff and not response_cutoff:
        print('\n')
        thinking = ''
        for tag in ['</think>', '<channel|>']:
            if tag in full_content:
                parts = full_content.rsplit(tag, 1)
                thinking = parts[0]
                full_content = parts[-1]
        if full_content.strip() == '':
            full_content = 'No Response'
        return ModelResponse(
            model='',
            response=full_content,
            thinking=thinking,
            input_tokens=_count_tokens(port, original_prompt),
            output_tokens=_count_tokens(port, thinking)
                         + _count_tokens(port, full_content),
        )

    # ----------------------------------------------------------------
    # Thinking cutoff — make a continuation request
    # ----------------------------------------------------------------
    if thinking_cutoff:
        # Estimate tokens from the (now cancelled) first stream
        total_output_tokens += max(output_tokens, token_count)

        # Build the continuation prompt
        if ('<think>' in full_content) or ('<think>' in original_prompt):
            continuation_prompt = (
                original_prompt
                + full_content
                + '</think>'
            )
        elif ('<|channel>thought' in full_content) or ('<|channel>thought' in original_prompt):
            continuation_prompt = (
                original_prompt
                + full_content
                + '<channel|>'
            )
        else:
            continuation_prompt = (
                original_prompt
                + full_content
                + '</think>'
            )

        # Prepare JSON for continuation — same parameters, new prompt
        continuation_data = dict(json_data)
        continuation_data['prompt'] = continuation_prompt
        continuation_data['stream'] = True

        # Remove n_predict if it is about to clash, but the user
        # asked us to keep it the same, so just forward it as-is.
        # (n_predict controls *additional* tokens to generate.)

        cont_url = f"http://127.0.0.1:{port}/completion"
        cont_resp = request('POST', cont_url, json=continuation_data,
                            stream=True)
        if cont_resp.status_code != 200:
            raise Exception(cont_resp.text)

        cont_content = ""
        cont_input_tokens = 0
        cont_output_tokens = 0
        cont_token_count = 0

        cont_response_cutoff = False

        for line in cont_resp.iter_lines():
            if not line:
                continue
            if line.startswith(b'data: '):
                try:
                    event_data = loads(line[len('data: '):])
                    token = event_data.get('content', '')
                    cont_content += token
                    cont_token_count += 1
                    if token:
                        print(token, end='', flush=True)
                    if event_data.get('stop', False):
                        timings = event_data.get('timings', {})
                        cont_input_tokens = timings.get('prompt_n', 0)
                        cont_output_tokens = timings.get('predicted_n', 0)
                        break
                    # ---- Repetition detection in continuation ----------
                    if _detect_repetition(cont_content):
                        print("\n==== CONTINUATION RESPONSE CUTOFF DUE TO REPETITION ====\n")
                        cont_response_cutoff = True
                        _force_close_response(cont_resp)
                        break
                except JSONDecodeError:
                    print(f"[ERROR] Invalid JSON: {line}", file=sys.stderr)

        total_output_tokens += max(cont_output_tokens, cont_token_count)
        # input_tokens stays from the original (or 0 if cut off) —
        # we deliberately *ignore* the continuation's prompt_n

        thinking = full_content
        final_response = cont_content
        print('\n')

        if final_response.strip() == '':
            final_response = 'No Response'

        return ModelResponse(
            model='',
            response=final_response,
            thinking=thinking,
            input_tokens=_count_tokens(port, original_prompt),
            output_tokens=_count_tokens(port, full_content)
                         + _count_tokens(port, final_response),
        )

    # ----------------------------------------------------------------
    # Response cutoff — return everything as-is, no continuation
    # ----------------------------------------------------------------
    if response_cutoff:
        print('\n')

        thinking = ''
        response_part = full_content
        for tag in ['</think>', '<channel|>']:
            if tag in full_content:
                parts = full_content.rsplit(tag, 1)
                thinking = parts[0]
                response_part = parts[-1]

        if response_part.strip() == '':
            response_part = 'No Response'

        return ModelResponse(
            model='',
            response=response_part,
            thinking=thinking,
            input_tokens=_count_tokens(port, original_prompt),
            output_tokens=_count_tokens(port, thinking)
                         + _count_tokens(port, response_part),
        )

def _stream_openai_compatible(
    json_data: dict,
    url: str,
    headers: dict,
    verify: str,
) -> ModelResponse:
    """Stream tokens from an OpenAI-compatible chat completions endpoint.

    Prints content and reasoning (thinking) tokens to stdout as they arrive.
    Detects repetition in the combined text and cancels the stream early.
    On cancellation for OpenRouter, queries the generation endpoint for token counts.
    Returns the accumulated full content as a ModelResponse.
    """
    json_data['stream'] = True
    print('=' * 30 + ' Begin Streaming Request ' + '=' * 30)
    print({'model': json_data.get('model', '?'), 'messages': json_data.get('messages', '?'), 'stream': True})
    print('=' * 30 + ' End Streaming Request ' + '=' * 30)
    print('=' * 30 + ' Begin Streaming Response ' + '=' * 30)
    response = request(
        method='POST',
        url=url,
        headers=headers,
        json=json_data,
        verify=verify,
        stream=True,
    )
    if response.status_code != 200:
        raise Exception(f"Stream error {response.status_code}: {response.text}")
    generation_id = response.headers.get('X-Generation-Id')
    full_content = ""
    full_thinking = ""
    input_tokens = 0
    output_tokens = 0
    buffer = bytearray()
    stream_finished = False
    stream_cancelled = False
    try:
        for chunk_bytes in response.iter_content(chunk_size=1024):
            if chunk_bytes:
                buffer.extend(chunk_bytes)

            while True:
                nl_idx = buffer.find(b'\n')
                if nl_idx == -1:
                    break

                line_bytes = buffer[:nl_idx]
                del buffer[:nl_idx + 1]

                line = line_bytes.decode('utf-8').rstrip('\r')

                if not line:
                    continue

                # Skip SSE comments
                if line.startswith(':'):
                    continue

                if not line.startswith('data: '):
                    continue

                data_str = line[6:]
                if data_str == '[DONE]':
                    stream_finished = True
                    break

                try:
                    chunk = loads(data_str)

                    if 'error' in chunk:
                        print(f"Stream error: {chunk['error'].get('message', 'unknown error')}")
                        stream_finished = True
                        break

                    usage = chunk.get('usage')
                    if usage:
                        input_tokens = usage.get('prompt_tokens', 0)
                        output_tokens = usage.get('completion_tokens', 0)

                    delta = chunk.get('choices', [{}])[0].get('delta', {})

                    content = delta.get('content', '') or ''
                    thinking = delta.get('reasoning', '') or ''

                    if content:
                        full_content += content
                        print(content, end="", flush=True)

                    if thinking:
                        full_thinking += thinking
                        print(thinking, end="", flush=True)

                    # ---- Repetition detection ---------------------------
                    if _detect_repetition(full_thinking + full_content):
                        print("\n==== STREAM CANCELLED DUE TO REPETITION ====\n")
                        stream_cancelled = True
                        _force_close_response(response)
                        break

                except JSONDecodeError:
                    pass

            if stream_finished or stream_cancelled:
                break
    finally:
        if not stream_cancelled:
            response.close()
    print('\n' + '=' * 30 + ' End Streaming Response ' + '=' * 30)
    if '</think>' in full_content:
        parts = full_content.split('</think>')
        full_thinking = parts[0] + (full_thinking if full_thinking else '')
        full_content = parts[-1]
    if full_content.strip() == '':
        if full_thinking.strip():
            full_content = full_thinking
        else:
            full_content = 'No Response'
    if stream_cancelled and generation_id:
        result_tokens = _query_generation_stats(
            url, headers, verify, generation_id,
        )
        if result_tokens is not None:
            input_tokens, output_tokens = result_tokens
    return ModelResponse(
        model='',
        response=full_content,
        thinking=full_thinking,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

def _query_generation_stats(
    url: str,
    headers: dict,
    verify: str,
    generation_id: str,
) -> t.Optional[tuple[int, int]]:
    """Query the generation endpoint for token counts after stream cancellation.

    Works for OpenRouter.  Returns None on failure (PUBLICAI does not expose
    this endpoint yet, so the counts stay at whatever the stream provided).
    """
    gen_url = url.replace('/chat/completions', '/generation')
    try:
        resp = request(
            'GET',
            gen_url,
            headers=headers,
            params={'id': generation_id},
            verify=verify,
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                data.get('tokens_prompt', 0),
                data.get('tokens_completion', 0),
            )
    except RequestException:
        pass
    return None


def get_llm(model_name: str) -> t.Union[LLaMaCPP, OpenRouterLLM, PublicAiLLM]:
    if model_name.startswith('OpenRouter'):
        llm = OpenRouterLLM()
    elif model_name.startswith('publicai'):
        llm = PublicAiLLM()
    elif model_name.endswith('.gguf'):
        llm = LLaMaCPP()
    else:
        raise Exception(f"Model {model_name} not found")
    llm.set_model(model_name)
    return llm


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

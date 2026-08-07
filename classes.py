from filetype import guess as guess_file_type
from hashlib import sha256
from datetime import datetime
from config import *
import typing as t


__all__ = ['TextContent', 'MediaContent', 'ToolCall', 'SystemMessage', 'UserMessage', 'AssistantMessage', 'MediaType', 'Conversation', 'ChatEntry', 'TextEntry', 'ToolMessage']


MediaType = t.Literal['image', 'audio', 'video', 'other_media']


class TextContent:
    def __init__(self, text: str):
        self._text = text

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"TextContent(text={self.text})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'type': 'text', 'text': self.text}

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, text: str) -> None:
        self._text = text


class MediaContent:
    def __init__(self, media_type: MediaType, hash_: t.Optional[str] = None, content: t.Optional[bytes] = None):
        self._media_type: MediaType = media_type
        self._hash = ''
        if hash_:
            self.hash_ = hash_
        elif content:
            self._save_content(content)
        else:
            raise ValueError('At least one of hash_ or content must be provided')

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"MediaContent(media_type={self.media_type}, hash={self.hash})"

    def __dict__(self) -> dict[str, str]:
        return {'type': self.media_type, 'hash': self.hash}

    def _save_content(self, content) -> None:
        self._hash = sha256(content).hexdigest()
        kind = guess_file_type(content)
        if not kind:
            extension = 'bin'
        else:
            extension = kind.extension
        match self._media_type:
            case 'image':
                base_location = IMAGE_LOCATION
            case 'audio':
                base_location = AUDIO_LOCATION
            case 'video':
                base_location = VIDEO_LOCATION
            case 'other_media':
                base_location = OTHER_MEDIA_LOCATION
            case _:
                base_location = OTHER_MEDIA_LOCATION
        base_location.mkdir(parents=True, exist_ok=True)
        with open(base_location / f"{self._hash}.{extension}", 'wb') as f:
            f.write(content)
        return None

    @property
    def hash(self) -> str:
        return self._hash

    @hash.setter
    def hash(self, hash_: str) -> None:
        self._hash = hash_

    @property
    def media_type(self) -> MediaType:
        return t.cast(MediaType, self._media_type)

    @media_type.setter
    def media_type(self, media_type: MediaType) -> None:
        self._media_type = media_type


class ToolCall:
    def __init__(self, name: str, arguments: dict[str, t.Any]):
        self._name = name
        self._arguments = arguments

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"ToolCall(name={self.name}, arguments={self.arguments})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'name': self.name, 'arguments': self.arguments}

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        self._name = name

    @property
    def arguments(self) -> dict[str, t.Any]:
        return self._arguments

    @arguments.setter
    def arguments(self, arguments: dict[str, t.Any]) -> None:
        self._arguments = arguments


class SystemMessage:
    def __init__(self, content: list[t.Union[TextContent, MediaContent]]):
        self._content = content

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"SystemMessage(content={self.content})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'role': 'system', 'content': [i.__dict__() for i in self.content]}

    @property
    def content(self) -> list[t.Union[TextContent, MediaContent]]:
        return self._content

    @content.setter
    def content(self, content: list[t.Union[TextContent, MediaContent]]) -> None:
        self._content = content


class UserMessage:
    def __init__(self, content: list[t.Union[TextContent, MediaContent]]):
        self._content = content

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"UserMessage(content={self.content})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'role': 'user', 'content': [i.__dict__() for i in self.content]}

    @property
    def content(self) -> list[t.Union[TextContent, MediaContent]]:
        return self._content

    @content.setter
    def content(self, content: list[t.Union[TextContent, MediaContent]]) -> None:
        self._content = content


class AssistantMessage:
    def __init__(self, text: TextContent, tool_calls: t.Optional[list[ToolCall]] = None):
        self._text = text
        if not tool_calls:
            tool_calls = []
        self._tool_calls = tool_calls

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"AssistantMessage(text={self.text}, tool_calls={self.tool_calls})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'role': 'assistant', 'text': self.text.__dict__(), 'tool_calls': [i.__dict__() for i in self.tool_calls]}

    @property
    def text(self) -> TextContent:
        return self._text

    @text.setter
    def text(self, text: TextContent) -> None:
        self._text = text

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self._tool_calls

    @tool_calls.setter
    def tool_calls(self, tool_calls: list[ToolCall]) -> None:
        self._tool_calls = tool_calls


class ToolMessage:
    def __init__(self, content: list[t.Union[TextContent, MediaContent]]):
        self._content = content

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"ToolMessage(content={self.content})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'role': 'tool', 'content': [i.__dict__() for i in self.content]}

    @property
    def content(self) -> list[t.Union[TextContent, MediaContent]]:
        return self._content

    @content.setter
    def content(self, content: list[t.Union[TextContent, MediaContent]]) -> None:
        self._content = content


class Conversation:
    def __init__(self, messages: list[t.Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]]):
        self._messages = messages

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Conversation(messages={self.messages})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'messages': [i.__dict__() for i in self.messages]}

    @property
    def messages(self) -> list[t.Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]]:
        return self._messages

    @messages.setter
    def messages(self, messages: list[t.Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]]) -> None:
        self._messages = messages


class ChatEntry:
    def __init__(self, messages: Conversation, source: str, collected_at: t.Optional[datetime] = None, ai_enhanced: bool = False):
        self._messages = messages
        self._source = source
        if not collected_at:
            collected_at = datetime.now()
        self._collected_at = collected_at
        self._ai_enhanced = ai_enhanced

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"ChatEntry(messages={self.messages}, source={self.source}, collected_at={self.collected_at}, ai_enhanced={self.ai_enhanced})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'messages': self.messages.__dict__(), 'source': self.source, 'collected_at': self.collected_at.isoformat(), 'ai_enhanced': self.ai_enhanced,}

    @property
    def messages(self) -> Conversation:
        return self._messages

    @messages.setter
    def messages(self, messages: Conversation) -> None:
        self._messages = messages

    @property
    def source(self) -> str:
        return self._source

    @source.setter
    def source(self, source: str) -> None:
        self._source = source

    @property
    def collected_at(self) -> datetime:
        return self._collected_at

    @collected_at.setter
    def collected_at(self, collected_at: datetime) -> None:
        self._collected_at = collected_at

    @property
    def ai_enhanced(self) -> bool:
        return self._ai_enhanced

    @ai_enhanced.setter
    def ai_enhanced(self, ai_enhanced: bool) -> None:
        self._ai_enhanced = ai_enhanced

class TextEntry:
    def __init__(self, text: str, source: str, collected_at: t.Optional[datetime] = None, ai_enhanced: bool = False):
        self._text = text
        self._source = source
        if not collected_at:
            collected_at = datetime.now()
        self._collected_at = collected_at
        self._ai_enhanced = ai_enhanced

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"TextEntry(text={self.text}, source={self.source}, collected_at={self.collected_at}, ai_enhanced={self.ai_enhanced})"

    def __dict__(self) -> dict[str, t.Any]:
        return {'text': self.text, 'source': self.source, 'collected_at': self.collected_at.isoformat(), 'ai_enhanced': self.ai_enhanced}

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, text: str) -> None:
        self._text = text

    @property
    def source(self) -> str:
        return self._source

    @source.setter
    def source(self, source: str) -> None:
        self._source = source

    @property
    def collected_at(self) -> datetime:
        return self._collected_at

    @collected_at.setter
    def collected_at(self, collected_at: datetime) -> None:
        self._collected_at = collected_at

    @property
    def ai_enhanced(self) -> bool:
        return self._ai_enhanced

    @ai_enhanced.setter
    def ai_enhanced(self, ai_enhanced: bool) -> None:
        self._ai_enhanced = ai_enhanced

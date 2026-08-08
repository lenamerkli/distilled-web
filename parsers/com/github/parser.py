import sys
sys.path.append('/home/lena/Documents/python/distilled-web')
from shutil import rmtree
from subprocess import run, check_output
from pathlib import Path
from urllib.parse import urlparse
from classes import *
from config import *
from writer import save


# Map file extensions to comment styles.
# Each entry: (line_comment, block_open, block_close) — use line_comment if set,
# otherwise wrap with block_open/block_close.
_COMMENT_STYLES: dict[str, tuple] = {
    # Line comments
    '.0': ('#', None, None),
    '.1': ('#', None, None),
    '.2': ('#', None, None),
    '.8': ('#', None, None),
    '.aarch64': ('#', None, None),
    '.ac': ('dnl ', None, None),
    '.accesswidener': ('#', None, None),
    '.aic79xx': ('#', None, None),
    '.aic7xxx': ('#', None, None),
    '.am': ('#', None, None),
    '.arch': ('#', None, None),
    '.arcmsr': ('#', None, None),
    '.arm': ('#', None, None),
    '.asan': ('#', None, None),
    '.asc': ('#', None, None),
    '.asm': (';', None, None),
    '.asm-headers': ('#', None, None),
    '.assembler': (';', None, None),
    '.autofdo': ('#', None, None),
    '.awk': ('#', None, None),
    '.bash': ('#', None, None),
    '.bat': ('REM ', None, None),
    '.bconf': ('#', None, None),
    '.bell': ('//', None, None),
    '.binfmt': ('#', None, None),
    '.boot': ('#', None, None),
    '.btf': ('#', None, None),
    '.build': ('#', None, None),
    '.bus': ('#', None, None),
    '.c': ('//', None, None),
    '.c_shipped': ('//', None, None),
    '.cat': ('//', None, None),
    '.cc': ('//', None, None),
    '.cfg': ('#', None, None),
    '.checkpatch': ('#', None, None),
    '.cjs': ('//', None, None),
    '.cl': ('//', None, None),
    '.clang': ('#', None, None),
    '.clang-format': ('#', None, None),
    '.clang-tidy': ('#', None, None),
    '.clean': ('#', None, None),
    '.clj': (';', None, None),
    '.cljc': (';', None, None),
    '.cljs': (';', None, None),
    '.cmake': ('#', None, None),
    '.cmd': ('REM ', None, None),
    '.cocci': ('//', None, None),
    '.common': ('#', None, None),
    '.compiler': ('#', None, None),
    '.comp': ('//', None, None),
    '.conf': ('#', None, None),
    '.config': ('#', None, None),
    '.context-analysis': ('#', None, None),
    '.cpp': ('//', None, None),
    '.cpu': ('#', None, None),
    '.cpufeatures': ('#', None, None),
    '.cputype': ('#', None, None),
    '.cr': ('#', None, None),
    '.cs': ('//', None, None),
    '.csv': ('#', None, None),
    '.cu': ('//', None, None),
    '.cuh': ('//', None, None),
    '.cxx': ('//', None, None),
    '.dart': ('//', None, None),
    '.def': ('//', None, None),
    '.default': ('#', None, None),
    '.defconf': ('#', None, None),
    '.deps': ('#', None, None),
    '.devices': ('#', None, None),
    '.dino': ('#', None, None),
    '.disabled': ('#', None, None),
    '.dockerfile': ('#', None, None),
    '.docs': ('#', None, None),
    '.dot': ('//', None, None),
    '.dtbinst': ('#', None, None),
    '.dtbs': ('#', None, None),
    '.dts': ('//', None, None),
    '.dtsi': ('//', None, None),
    '.dtso': ('//', None, None),
    '.editorconfig': ('#', None, None),
    '.el': (';', None, None),
    '.env': ('#', None, None),
    '.erl': ('%', None, None),
    '.errata': ('#', None, None),
    '.exceptions': ('#', None, None),
    '.ex': ('#', None, None),
    '.example': ('#', None, None),
    '.expected': ('#', None, None),
    '.exs': ('#', None, None),
    '.farf': ('#', None, None),
    '.feature': ('#', None, None),
    '.fish': ('#', None, None),
    '.flashpoint': ('#', None, None),
    '.fluidrendererfactory': ('#', None, None),
    '.frag': ('//', None, None),
    '.frapiregistrarprovider': ('#', None, None),
    '.freezer': ('#', None, None),
    '.fs': ('//', None, None),
    '.fsh': ('//', None, None),
    '.fsx': ('//', None, None),
    '.fuc': ('//', None, None),
    '.fuc0s': ('//', None, None),
    '.fuc3': ('//', None, None),
    '.fuc4': ('//', None, None),
    '.fuc5': ('//', None, None),
    '.gbnf': ('#', None, None),
    '.gcc-plugins': ('#', None, None),
    '.gemspec': ('#', None, None),
    '.genkey': ('#', None, None),
    '.gitattributes': ('#', None, None),
    '.gitignore': ('#', None, None),
    '.gitmodules': ('#', None, None),
    '.glsl': ('//', None, None),
    '.go': ('//', None, None),
    '.gradle': ('//', None, None),
    '.graphicsbootstrapper': ('#', None, None),
    '.groovy': ('//', None, None),
    '.h': ('//', None, None),
    '.h_shipped': ('//', None, None),
    '.hardening': ('#', None, None),
    '.hcl': ('#', None, None),
    '.headersinst': ('#', None, None),
    '.hex': ('#', None, None),
    '.hh': ('//', None, None),
    '.host': ('#', None, None),
    '.hp300': ('#', None, None),
    '.hpp': ('//', None, None),
    '.hrl': ('%', None, None),
    '.hs': ('--', None, None),
    '.hxx': ('//', None, None),
    '.hz': ('#', None, None),
    '.i686': ('#', None, None),
    '.idl': ('//', None, None),
    '.ids': ('#', None, None),
    '.ignore': ('#', None, None),
    '.iml': ('#', None, None),
    '.in': ('#', None, None),
    '.inc': ('//', None, None),
    '.inc1': ('//', None, None),
    '.inc2': ('//', None, None),
    '.inc3': ('//', None, None),
    '.inc_shipped': ('//', None, None),
    '.include': ('//', None, None),
    '.inf': ('#', None, None),
    '.ini': (';', None, None),
    '.inl': ('//', None, None),
    '.iosched': ('#', None, None),
    '.ips': ('#', None, None),
    '.java': ('//', None, None),
    '.jl': ('#', None, None),
    '.js': ('//', None, None),
    '.jsx': ('//', None, None),
    '.kasan': ('#', None, None),
    '.kconfig': ('#', None, None),
    '.kcov': ('#', None, None),
    '.kcsan': ('#', None, None),
    '.kexec': ('#', None, None),
    '.kfence': ('#', None, None),
    '.kgdb': ('#', None, None),
    '.kmsan': ('#', None, None),
    '.kt': ('//', None, None),
    '.kts': ('//', None, None),
    '.kstack_erase': ('#', None, None),
    '.kvm': ('#', None, None),
    '.lark': ('//', None, None),
    '.lds': ('//', None, None),
    '.less': ('//', None, None),
    '.litmus': ('//', None, None),
    '.locking': ('#', None, None),
    '.locks': ('#', None, None),
    '.log': ('#', None, None),
    '.lpfc': ('#', None, None),
    '.lua': ('--', None, None),
    '.m': ('%', None, None),
    '.m4': ('dnl ', None, None),
    '.machine': ('#', None, None),
    '.mak': ('#', None, None),
    '.makefile': ('#', None, None),
    '.mca': ('#', None, None),
    '.megaraid': ('#', None, None),
    '.megaraid_sas': ('#', None, None),
    '.metal': ('//', None, None),
    '.mf': ('#', None, None),
    '.mips': ('#', None, None),
    '.mjs': ('//', None, None),
    '.mk': ('#', None, None),
    '.mm': ('//', None, None),
    '.mod': ('#', None, None),
    '.modes': ('#', None, None),
    '.modfinal': ('#', None, None),
    '.modinst': ('#', None, None),
    '.modpost': ('#', None, None),
    '.msm': ('#', None, None),
    '.mtl': ('#', None, None),
    '.nim': ('#', None, None),
    '.nix': ('#', None, None),
    '.nolibc': ('#', None, None),
    '.nvim': ('"', None, None),
    '.obj': ('#', None, None),
    '.orderfile': ('#', None, None),
    '.out': ('#', None, None),
    '.package': ('#', None, None),
    '.patch': ('#', None, None),
    '.pbm': ('#', None, None),
    '.pem': ('#', None, None),
    '.perf': ('#', None, None),
    '.perl': ('#', None, None),
    '.php': ('//', None, None),
    '.pkt': ('#', None, None),
    '.pl': ('#', None, None),
    '.platform': ('#', None, None),
    '.platformblockaccess': ('#', None, None),
    '.platformlevelaccess': ('#', None, None),
    '.platformlevelrenderhooks': ('#', None, None),
    '.platformmixinoverrides': ('#', None, None),
    '.platformmodelaccess': ('#', None, None),
    '.platformmodelemitterprovider': ('#', None, None),
    '.platformruntimeinformation': ('#', None, None),
    '.platforms': ('#', None, None),
    '.pm': ('#', None, None),
    '.postlink': ('#', None, None),
    '.powerpc': ('#', None, None),
    '.ppc64el': ('#', None, None),
    '.ppc64le': ('#', None, None),
    '.ppm': ('#', None, None),
    '.preempt': ('#', None, None),
    '.pro': ('#', None, None),
    '.profile': ('#', None, None),
    '.propeller': ('#', None, None),
    '.properties': ('#', None, None),
    '.ps1': ('#', None, None),
    '.py': ('#', None, None),
    '.pyw': ('#', None, None),
    '.r': ('#', None, None),
    '.randstruct': ('#', None, None),
    '.rb': ('#', None, None),
    '.rbs': ('#', None, None),
    '.readme': ('#', None, None),
    '.recursion-issue-01': ('#', None, None),
    '.recursion-issue-02': ('#', None, None),
    '.reg': ('//', None, None),
    '.riscv': ('#', None, None),
    '.riscv64': ('#', None, None),
    '.rs': ('//', None, None),
    '.rtla': ('#', None, None),
    '.rules': ('#', None, None),
    '.rv': ('#', None, None),
    '.S': ('#', None, None),
    '.s': ('#', None, None),
    '.s390x': ('#', None, None),
    '.s3c64xx': ('#', None, None),
    '.sa': (';', None, None),
    '.sample': ('#', None, None),
    '.sass': ('//', None, None),
    '.scala': ('//', None, None),
    '.schema': ('#', None, None),
    '.scl': ('#', None, None),
    '.scss': ('//', None, None),
    '.scr': ('//', None, None),
    '.script': ('//', None, None),
    '.sed': ('#', None, None),
    '.select-break': ('#', None, None),
    '.seq': ('//', None, None),
    '.service': ('#', None, None),
    '.sh': ('#', None, None),
    '.socs': ('#', None, None),
    '.spec': ('#', None, None),
    '.sql': ('--', None, None),
    '.src': ('#', None, None),
    '.standalone': ('#', None, None),
    '.stb': ('#', None, None),
    '.styl': ('//', None, None),
    '.sum': ('#', None, None),
    '.swift': ('//', None, None),
    '.swg': ('//', None, None),
    '.sym53c8xx': ('#', None, None),
    '.sym53c8xx_2': ('#', None, None),
    '.syscalls': ('#', None, None),
    '.t': ('#', None, None),
    '.target': ('#', None, None),
    '.tbl': ('#', None, None),
    '.tc': ('#', None, None),
    '.template': ('#', None, None),
    '.test': ('#', None, None),
    '.tf': ('#', None, None),
    '.thinlto': ('#', None, None),
    '.tmpl': ('#', None, None),
    '.tng': ('#', None, None),
    '.toml': ('#', None, None),
    '.ts': ('//', None, None),
    '.tsx': ('//', None, None),
    '.txt': ('#', None, None),
    '.typed': ('#', None, None),
    '.ubsan': ('#', None, None),
    '.uc': ('//', None, None),
    '.um': ('#', None, None),
    '.uni': ('#', None, None),
    '.unit': ('#', None, None),
    '.userprogs': ('#', None, None),
    '.utf8data': ('#', None, None),
    '.vb': ("'", None, None),
    '.vdsoinst': ('#', None, None),
    '.vendor': ('#', None, None),
    '.vert': ('//', None, None),
    '.vim': ('"', None, None),
    '.vm': ('#', None, None),
    '.vmlinux': ('#', None, None),
    '.vmlinux_a': ('#', None, None),
    '.vmlinux_o': ('#', None, None),
    '.vsh': ('//', None, None),
    '.warn': ('#', None, None),
    '.warning': ('#', None, None),
    '.wgsl': ('//', None, None),
    '.x': ('//', None, None),
    '.x86': ('#', None, None),
    '.x86-64': ('#', None, None),
    '.x86_64': ('#', None, None),
    '.xs': ('//', None, None),
    '.yaml': ('#', None, None),
    '.yml': ('#', None, None),
    '.zboot': ('#', None, None),
    '.zig': ('//', None, None),
    '.zsh': ('#', None, None),
    # Block comments
    '.astro': (None, '<!--', '-->'),
    '.bbmodel': (None, '/*', '*/'),
    '.bc': (None, '/*', '*/'),
    '.bt': (None, '/*', '*/'),
    '.css': (None, '/*', '*/'),
    '.donotload': ('#', None, None),
    '.entitlements': (None, '<!--', '-->'),
    '.gql': (None, '#', ''),
    '.graphql': (None, '#', ''),
    '.htm': (None, '<!--', '-->'),
    '.html': (None, '<!--', '-->'),
    '.inp': (None, '/*', '*/'),
    '.j2': (None, '{#', '#}'),
    '.jinja': (None, '{#', '#}'),
    '.json': (None, '/*', '*/'),
    '.json5': (None, '/*', '*/'),
    '.jsonc': (None, '/*', '*/'),
    '.l': (None, '/*', '*/'),
    '.last': (None, '/*', '*/'),
    '.ld': (None, '/*', '*/'),
    '.markdown': (None, '<!--', '-->'),
    '.mcmeta': (None, '/*', '*/'),
    '.md': (None, '<!--', '-->'),
    '.mdx': (None, '<!--', '-->'),
    '.pbxproj': (None, '<!--', '-->'),
    '.peb': (None, '{#', '#}'),
    '.plist': (None, '<!--', '-->'),
    '.po': (None, '/*', '*/'),
    '.proto': (None, '/*', '*/'),
    '.rst': (None, '..', ''),
    '.storyboard': (None, '<!--', '-->'),
    '.svg': (None, '<!--', '-->'),
    '.svelte': (None, '<!--', '-->'),
    '.tex': (None, '%', ''),
    '.ui': (None, '<!--', '-->'),
    '.vue': (None, '<!--', '-->'),
    '.webmanifest': (None, '/*', '*/'),
    '.xcworkspacedata': (None, '<!--', '-->'),
    '.xml': (None, '<!--', '-->'),
    '.xpm': (None, '/*', '*/'),
    '.xcscheme': (None, '<!--', '-->'),
    '.xsd': (None, '<!--', '-->'),
    '.xsl': (None, '<!--', '-->'),
    '.y': (None, '/*', '*/'),
    # TeX / BibTeX
    '.bib': ('%', None, None),
    '.sty': ('%', None, None),
    # ASN.1
    '.asn1': ('--', None, None),
}

# Fallback comment style for unknown extensions.
_FALLBACK_STYLE = (None, '# <!--', '-->')

# Special-case filenames (no extension) → comment style.
_NAMED_FILES: dict[str, tuple] = {
    '.clang-format': ('#', None, None),
    '.clang-tidy': ('#', None, None),
    '.cocciconfig': ('#', None, None),
    '.dockerignore': ('#', None, None),
    '.document': ('#', None, None),
    '.ecrc': ('#', None, None),
    '.editorconfig': ('#', None, None),
    '.env': ('#', None, None),
    '.flake8': ('#', None, None),
    '.gitattributes': ('#', None, None),
    '.gitignore': ('#', None, None),
    '.gitkeep': ('#', None, None),
    '.gitmodules': ('#', None, None),
    '.kunitconfig': ('#', None, None),
    '.mailmap': ('#', None, None),
    '.name': ('#', None, None),
    '.npmrc': ('#', None, None),
    '.prettierignore': ('#', None, None),
    '.prettierrc': (None, '/*', '*/'),
    '.pylintrc': ('#', None, None),
    '.rdoc_options': ('#', None, None),
    '.yamllint': ('#', None, None),
    'aclocal.m4': _COMMENT_STYLES['.m4'],
    'ar-lib': _COMMENT_STYLES['.sh'],
    'authors': _COMMENT_STYLES['.txt'],
    'build.gradle': _COMMENT_STYLES['.gradle'],
    'cargo.lock': _COMMENT_STYLES['.toml'],
    'cargo.toml': _COMMENT_STYLES['.toml'],
    'changelog': _COMMENT_STYLES['.md'],
    'changes': _COMMENT_STYLES['.txt'],
    'cmakelists.txt': _COMMENT_STYLES['.cmake'],
    'code_of_conduct': _COMMENT_STYLES['.md'],
    'codeowners': ('#', None, None),
    'codingstyle': _COMMENT_STYLES['.txt'],
    'compile': _COMMENT_STYLES['.sh'],
    'composer.json': _COMMENT_STYLES['.json'],
    'config.guess': _COMMENT_STYLES['.sh'],
    'config.h': _COMMENT_STYLES['.c'],
    'config.h.in': _COMMENT_STYLES['.c'],
    'config.log': _COMMENT_STYLES['.txt'],
    'config.status': _COMMENT_STYLES['.sh'],
    'config.sub': _COMMENT_STYLES['.sh'],
    'configure': _COMMENT_STYLES['.sh'],
    'configure.ac': _COMMENT_STYLES['.sh'],
    'configure.in': _COMMENT_STYLES['.sh'],
    'contributing': _COMMENT_STYLES['.md'],
    'copying': _COMMENT_STYLES['.txt'],
    'credits': _COMMENT_STYLES['.txt'],
    'depcomp': _COMMENT_STYLES['.sh'],
    'docker-compose.yaml': _COMMENT_STYLES['.yaml'],
    'docker-compose.yml': _COMMENT_STYLES['.yaml'],
    'dockerfile': _COMMENT_STYLES['.dockerfile'],
    'flake.lock': _COMMENT_STYLES['.json'],
    'gemfile': _COMMENT_STYLES['.rb'],
    'gemfile.lock': _COMMENT_STYLES['.rb'],
    'go.mod': _COMMENT_STYLES['.go'],
    'go.sum': _COMMENT_STYLES['.go'],
    'gradlew': _COMMENT_STYLES['.sh'],
    'install-sh': _COMMENT_STYLES['.sh'],
    'jenkinsfile': ('//', None, None),
    'justfile': _COMMENT_STYLES['.makefile'],
    'license': _COMMENT_STYLES['.txt'],
    'ltmain.sh': _COMMENT_STYLES['.sh'],
    'maintainers': _COMMENT_STYLES['.txt'],
    'makefile': _COMMENT_STYLES['.makefile'],
    'makefile.am': _COMMENT_STYLES['.makefile'],
    'makefile.in': _COMMENT_STYLES['.makefile'],
    'meson.build': _COMMENT_STYLES['.py'],
    'missing': _COMMENT_STYLES['.sh'],
    'mix.lock': _COMMENT_STYLES['.ex'],
    'mkinstalldirs': _COMMENT_STYLES['.sh'],
    'notice': _COMMENT_STYLES['.txt'],
    'package-lock.json': _COMMENT_STYLES['.json'],
    'package.json': _COMMENT_STYLES['.json'],
    'pipfile': _COMMENT_STYLES['.toml'],
    'pipfile.lock': _COMMENT_STYLES['.json'],
    'pnpm-lock.yaml': _COMMENT_STYLES['.yaml'],
    'poetry.lock': _COMMENT_STYLES['.toml'],
    'pom.xml': _COMMENT_STYLES['.xml'],
    'procfile': _COMMENT_STYLES['.sh'],
    'pubspec.lock': _COMMENT_STYLES['.yaml'],
    'py-compile': _COMMENT_STYLES['.sh'],
    'pyproject.toml': _COMMENT_STYLES['.toml'],
    'rakefile': _COMMENT_STYLES['.rb'],
    'readme': _COMMENT_STYLES['.md'],
    'requirements.txt': _COMMENT_STYLES['.txt'],
    'security': _COMMENT_STYLES['.md'],
    'settings.gradle': _COMMENT_STYLES['.gradle'],
    'setup.cfg': _COMMENT_STYLES['.cfg'],
    'speak': _COMMENT_STYLES['.sh'],
    'stamp-h.in': _COMMENT_STYLES['.txt'],
    'stamp-h1': _COMMENT_STYLES['.txt'],
    'submittingpatches': _COMMENT_STYLES['.txt'],
    'test-driver': _COMMENT_STYLES['.sh'],
    'thanks': _COMMENT_STYLES['.txt'],
    'todo': _COMMENT_STYLES['.txt'],
    'tsconfig.json': _COMMENT_STYLES['.json'],
    'vagrantfile': _COMMENT_STYLES['.rb'],
    'yarn.lock': _COMMENT_STYLES['.yaml'],
}

# Extensions that are always treated as non-text (binary).
_BINARY_EXTENSIONS = {
    '.7z',
    '.a',
    '.aac',
    '.arrow',
    '.avi',
    '.bin',
    '.bmp',
    '.bz2',
    '.class',
    '.dat',
    '.db',
    '.deb',
    '.debug',
    '.dll',
    '.dmg',
    '.doc',
    '.docx',
    '.dylib',
    '.ear',
    '.egg',
    '.eot',
    '.exe',
    '.flac',
    '.flv',
    '.gguf',
    '.gif',
    '.gz',
    '.h5',
    '.hdf5',
    '.ico',
    '.img',
    '.ipynb_checkpoints',
    '.iso',
    '.jar',
    '.joblib',
    '.jpeg',
    '.jpg',
    '.key',
    '.lib',
    '.m4a',
    '.map',
    '.mkv',
    '.mov',
    '.mp3',
    '.mp4',
    '.nbt',
    '.npy',
    '.npz',
    '.o',
    '.obj',
    '.ogg',
    '.onnx',
    '.otf',
    '.parquet',
    '.pb',
    '.pdf',
    '.pickle',
    '.pkl',
    '.png',
    '.ppt',
    '.pptx',
    '.profraw',
    '.pyc',
    '.pyd',
    '.pyo',
    '.rar',
    '.rpm',
    '.so',
    '.sqlite',
    '.sqlite3',
    '.svgz',
    '.swf',
    '.tar',
    '.tflite',
    '.tiff',
    '.ttf',
    '.war',
    '.wasm',
    '.wav',
    '.webm',
    '.webp',
    '.whl',
    '.wmv',
    '.woff',
    '.woff2',
    '.xls',
    '.xlsx',
    '.xz',
    '.zip',
}


def _comment_style(path: Path) -> tuple:
    """Return the (line_comment, block_open, block_close) style for a file."""
    name = path.name.lower()
    if name in _NAMED_FILES:
        return _NAMED_FILES[name]
    return _COMMENT_STYLES.get(path.suffix.lower(), _FALLBACK_STYLE)


def _build_comment(path: Path, repo_name: str, temp_dir: Path, branch: str) -> str:
    """Build a language-aware comment header with file path and repo name."""
    line_comment, block_open, block_close = _comment_style(path)
    rel_path = path.relative_to(temp_dir).as_posix()
    branch_suffix = f" | Branch: {branch}" if branch not in ('main', 'master') else ""
    if line_comment:
        return f"{line_comment} File: {rel_path}\n{line_comment} Repository: {repo_name}{branch_suffix}\n\n"
    if block_close:
        return f"{block_open} File: {rel_path} | Repository: {repo_name}{branch_suffix} {block_close}\n\n"
    return f"{block_open} File: {rel_path} | Repository: {repo_name}{branch_suffix}\n\n"


def _read_text(path: Path) -> str | None:
    """Read a file as UTF-8 text, or return None if it's not a text file."""
    if path.suffix.lower() in _BINARY_EXTENSIONS:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b'\x00' in data:
        return None
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _parse_repo(url: str) -> tuple[str, str, str | None]:
    """Extract (owner, repo, branch) from a GitHub URL.

    Branch is None when the URL points to the whole repo (all branches),
    e.g. https://github.com/ggml-org/llama.cpp
    Otherwise it's the branch after '/tree/', e.g.
    https://github.com/ggml-org/llama.cpp/tree/gg/tts-fix-ubatch
    """
    parsed = urlparse(url)
    if parsed.netloc.lower() != 'github.com':
        raise ValueError(f'Not a GitHub URL: {url}')
    parts = [seg for seg in parsed.path.split('/') if seg]
    if len(parts) < 2:
        raise ValueError(f'Cannot determine owner/repo from URL: {url}')
    owner, repo = parts[0], parts[1]
    branch = None
    if len(parts) > 2 and parts[2] == 'tree':
        branch = '/'.join(parts[3:])
        if not branch:
            raise ValueError(f'Cannot determine branch from URL: {url}')
    return owner, repo, branch


def _list_branches(temp_dir: Path) -> list[str]:
    """Return the list of remote branch names (without 'origin/' prefix)."""
    out = check_output(['git', 'branch', '-r'], cwd=temp_dir, text=True)
    branches = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('origin/HEAD'):
            continue
        branches.append(line.removeprefix('origin/'))
    return branches


def parse(url: str):
    owner, repo, branch = _parse_repo(url)
    repo_name = f'{owner}/{repo}'
    # Clean repo URL without any '/tree/...' path, used for git clone.
    clone_url = f'https://github.com/{owner}/{repo}'
    temp_dir = TMP_LOCATION / f'com.github.{owner}.{repo}'

    # Clean up any stale temp dir.
    if temp_dir.exists() or temp_dir.is_symlink():
        rmtree(temp_dir)

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        if branch:
            # Single-branch clone: only the requested branch.
            run(
                ['git', 'clone', '--depth', '1', '--branch', branch, '--single-branch', clone_url, str(temp_dir)],
                check=True,
            )
            branches = [branch]
        else:
            # Whole-repo clone: all branches.
            run(
                ['git', 'clone', '--depth', '1', '--no-single-branch', clone_url, str(temp_dir)],
                check=True,
            )
            branches = _list_branches(temp_dir)
            if not branches:
                branches = ['main']

        for b in branches:
            run(['git', 'checkout', b], cwd=temp_dir, check=True)
            for path in temp_dir.rglob('*'):
                if not path.is_file():
                    continue
                if '.git' in path.parts:
                    continue
                text = _read_text(path)
                if text is None:
                    continue
                # First save: raw file content.
                save(TextEntry(text, source=url))
                # Second save: with language-aware comment header.
                comment = _build_comment(path, repo_name, temp_dir, b)
                save(TextEntry(comment + text, source=url))
    finally:
        if temp_dir.exists() or temp_dir.is_symlink():
            rmtree(temp_dir)

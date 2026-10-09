"""Keep Python quoting out of Windows PowerShell argument handling."""
import sys
from faster_whisper.utils import download_model

if __name__ == '__main__':
    print(download_model('large-v3', cache_dir=sys.argv[1]))

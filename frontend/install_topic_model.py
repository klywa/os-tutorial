"""Install pinned official CPU assets with resumable, checksum-verified downloads."""
import argparse,hashlib,json,subprocess,zipfile,tempfile,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODEL_URL='https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q8_0.gguf'
MODEL_SHA='061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a'
RUNTIME_URL='https://github.com/ggml-org/llama.cpp/releases/download/b11712/llama-b11712-bin-win-cpu-x64.zip'
RUNTIME_SHA='cc8454164d885e6826a06abd6100aa040b5b5139d527ae49058ec7c449011b68'

def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def download(url,path,sha):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.is_file() and digest(path)==sha:return
 part=path.with_suffix(path.suffix+'.part')
 if not part.is_file() or digest(part)!=sha:
  subprocess.run(['curl.exe','--fail','--location','--retry','3','--retry-delay','2','--continue-at','-','--output',str(part),url],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if not part.is_file() or digest(part)!=sha:raise ValueError('下载校验失败，旧文件保持不变，已保留.part供检查或续传：'+path.name)
 os.replace(part,path)

def install(verify_only=False):
 folder=ROOT/'.wxq-runtime/llm';model=folder/'Qwen3-1.7B-Q8_0.gguf';archive=folder/'llama-b11712-win-cpu.zip'
 for url,path,sha in [(MODEL_URL,model,MODEL_SHA),(RUNTIME_URL,archive,RUNTIME_SHA)]:
  if verify_only:
   if not path.is_file() or digest(path)!=sha:raise ValueError('缺失或校验失败：'+path.name)
  else:download(url,path,sha)
 target=folder/'bin-b11712'
 if not verify_only and not target.exists():
  with tempfile.TemporaryDirectory(prefix='install-',dir=folder) as temporary:
   stage=Path(temporary)/'bin';stage.mkdir()
   with zipfile.ZipFile(archive) as zipped:
    for member in zipped.infolist():
     if not (stage/member.filename).resolve().is_relative_to(stage.resolve()):raise ValueError('运行时压缩包路径无效')
    zipped.extractall(stage)
   os.replace(stage,target)
 if not target.exists():target=folder/'bin'  # Existing installation from the first download.
 with zipfile.ZipFile(archive) as zipped:
  for member in zipped.infolist():
   if member.is_dir():continue
   path=(target/member.filename).resolve()
   if not path.is_relative_to(target.resolve()) or not path.is_file() or digest(path)!=hashlib.sha256(zipped.read(member)).hexdigest():raise ValueError('运行时文件校验失败：'+member.filename)
 manifest={'model':'Qwen/Qwen3-1.7B-GGUF','file':model.name,'sha256':MODEL_SHA,'model_url':MODEL_URL,'runtime':'llama.cpp b11712','runtime_url':RUNTIME_URL,'runtime_sha256':RUNTIME_SHA,'runtime_directory':str(target.relative_to(folder))}
 if not verify_only:
  temporary=folder/'manifest.json.tmp';temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8');os.replace(temporary,folder/'manifest.json')
 return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true');args=parser.parse_args()
 print(json.dumps(install(args.verify_only),ensure_ascii=False,indent=2))

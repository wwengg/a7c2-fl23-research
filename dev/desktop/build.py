"""Build on the native host; Windows output paths remain unchanged."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from profilepack import files as profile_files

ROOT = Path(__file__).resolve().parents[2]


def make_dmg(output):
    output=Path(output).resolve()
    app=output/'A7C2Tools.app'
    if not app.is_dir():raise FileNotFoundError(app)
    target=output/('A7C2Tools-macOS-'+platform.machine()+'.dmg')
    # Temporary staging prevents files from older builds leaking into the DMG.
    with tempfile.TemporaryDirectory(prefix='a7c2-dmg-',dir=output) as temporary:
        staging=Path(temporary)
        shutil.copytree(app,staging/app.name,symlinks=True)
        (staging/'Applications').symlink_to('/Applications',target_is_directory=True)
        # On Intel the restored Zig binary cannot be signed (see restore_zig),
        # so the bundle is unsigned and deep verification cannot apply.
        if platform.machine()!='x86_64':
            subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
        subprocess.run(['hdiutil','create','-ov','-format','UDZO','-volname',
                        'A7C II Tools','-srcfolder',str(staging),str(target)],check=True)
    subprocess.run(['hdiutil','verify',str(target)],check=True)
    return target


def restore_zig(app):
    """Keep the x86_64 Zig executable working; it cannot survive signing.

    PyInstaller ad-hoc signs every collected Mach-O binary. On x86_64 that
    signature corrupts the ~180 MB ziglang executable: its clang frontend
    segfaults on every `zig cc` cross compile (arm64 is unaffected). Restore
    the untouched wheel binary verbatim and drop the now-invalid bundle
    signature; Intel packages therefore ship unsigned, matching the arm64
    packages which carry no Developer ID either."""
    spec=importlib.util.find_spec('ziglang')
    for folder in spec.submodule_search_locations or []:
        source=Path(folder)/'zig'
        if source.is_file():break
    else:raise FileNotFoundError('ziglang executable not found in the build environment')
    shutil.copy2(source,app/'Contents/Frameworks/ziglang/zig')
    subprocess.run(['codesign','--remove-signature',str(app)],check=True)


def make_windows_zip(output):
    output=Path(output)
    target=output/'A7C2Tools-Windows-x64.zip'
    library=profile_files()
    for relative,source in library.items():
        dest=output/'A7C2Tools/Profiles'/relative
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    shutil.copyfile(ROOT/'README.md',output/'A7C2Tools/README.md')
    shutil.copyfile(ROOT/'README.zh-CN.md',output/'A7C2Tools/README.zh-CN.md')
    shutil.copyfile(ROOT/'LICENSE',output/'A7C2Tools/LICENSE')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as stream:
        for source in sorted((output/'A7C2Tools').rglob('*')):
            relative=source.relative_to(output/'A7C2Tools')
            # Users may save diagnostic ZIPs beside the executable. Never
            # redistribute those local files in the next development bundle.
            if relative.parts[0] not in ('A7C2Tools.exe','_internal','README.md','README.zh-CN.md','LICENSE','VERSION.txt'):continue
            if relative.parts[:3]==('_internal','desktop-assets','profile-library-v1'):continue
            if source.is_file():stream.write(source,source.relative_to(output))
        for relative,source in library.items():stream.write(source,'A7C2Tools/Profiles/'+relative)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    if sys.platform not in ('win32','darwin'):raise RuntimeError('Build on native Windows or macOS')
    if sys.platform=='darwin' and platform.machine() not in ('arm64','x86_64'):
        raise RuntimeError('macOS packaging supports arm64 and x86_64 hosts only')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    profile_files()
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm',
                    '--distpath',str(output),'--workpath',str(ROOT/'build/desktop'),
                    str(ROOT/'dev/desktop/desktop.spec')],cwd=ROOT,check=True)
    if sys.platform=='darwin' and platform.machine()=='x86_64':restore_zig(output/'A7C2Tools.app')
    target=make_dmg(output) if sys.platform=='darwin' else make_windows_zip(output)
    print(json.dumps(dict(artifact=str(target),bytes=target.stat().st_size,camera_io=False)))


if __name__=='__main__':main()

# 安装

## Windows

下载 [exe 文件](https://github.com/nachifur/MulimgViewer/releases)：

- 安装版 `*_Setup.exe` （启动速度更快）
- 便携版 `*_Portable.exe`

## [PYPI](https://pypi.org/project/mulimgviewer/) (测试中)

任何安装了 [`pip`](https://github.com/pypa/pip) 的系统均可：

```sh
pip install mulimgviewer
# if you want a prompt when this program has a new version
pip install mulimgviewer[update]
```

注意，目前由于依赖项 [wxpython](https://github.com/wxWidgets/Phoenix)
的 [bug](https://github.com/wxWidgets/Phoenix/issues/2225)，该方法可能会失败。

![icon](https://user-images.githubusercontent.com/32936898/224473440-2088edd7-42e5-45a3-a403-515e2daa019a.jpg)

## [AUR](https://aur.archlinux.org/packages/python-mulimgviewer)

任何安装了 [`pacman`](https://archlinux.org/pacman/) 的系统均可（尽管目前仅在
`ArchLinux` 上测试过）：

- [ArchLinux](https://archlinux.org/)
- Other Linux distributions with pacman
- Windows with [Msys2](https://www.msys2.org/)
- Android with [Termux-pacman](https://github.com/termux-pacman)

通过[AUR 助手](https://wiki.archlinuxcn.org/wiki/AUR_%E5%8A%A9%E6%89%8B)安装：

```sh
yay -S python-mulimgviewer
```

## brew

任何安装了 [`brew`](https://github.com/Homebrew/brew) 的系统均可：

- Any Linux distributions with linuxbrew
- macOS with homebrew

```sh
brew tap nachifur/MulimgViewer https://github.com/nachifur/MulimgViewer
brew install python-mulimgviewer
```

## PPA （TODO）

目前该软件还没有打包到 Ubuntu PPA 上。

这是一个临时的安装方法，它避开了 `wxpython` 的 bug：

```sh
sudo apt install python3-wxgtk4.0
git clone --depth=1 https://github.com/nachifur/MulimgViewer
cd MulimgViewer
sed -i /wxpython/d requirements.txt
pip install .
```

## Nix

任何安装了 [`nix`](https://github.com/NixOS/nix) 的系统均可：

- Nix OS
- Other Linux distributions with nix
- macOS with nix-darwin

For NixOS, add the following code to `/etc/nixos/configuration.nix`:

```nix
{ config, pkgs, ... }:
{
  nix.settings.experimental-features = [ "flakes" ];
  environment.systemPackages =
    let
      mulimgviewer = (
        builtins.getFlake "github:nachifur/MulimgViewer"
      ).packages.${builtins.currentSystem}.default;
    in
    [
      mulimgviewer
    ];
}
```

For nix,

```sh
nix shell github:nachifur/MulimgViewer
```

Or just take a try without installation:

```sh
nix run github:nachifur/MulimgViewer
```

## 运行源码 | 适合所有系统，需自行构建python环境
* **任何系统**都可以使用源码运行
* 安装python环境可以使用`pip` or `conda`
* 建议使用Python3.6以上
* [最新源码下载](https://codeload.github.com/nachifur/MulimgViewer/zip/refs/heads/master)

### 1. pip 安装
pip安装：（如果安装过程出错，可以使用conda安装）
```bash
pip install wxpython pillow pytest-shutil numpy requests piexif
```
运行：
```python
python MulimgViewer.py
```
### 2. conda 安装
或者安装conda环境：
```bash
conda env create -f install.yaml
```
运行：
```python
conda activate mulimgviewer
python MulimgViewer.py
```

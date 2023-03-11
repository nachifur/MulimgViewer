# 安装

## [PYPI](https://pypi.org/project/mulimgviewer/)

任何安装了 [`pip`](https://github.com/pypa/pip) 的系统均可：

- 所有 `python` 支持的系统 (`pip` 是用 `python` 写的)

```sh
pip install mulimgviewer
# if you want a prompt when this program has a new version
pip install mulimgviewer[update]
```

注意，目前由于依赖项 [wxpython](https://github.com/wxWidgets/Phoenix)
的 [bug](https://github.com/wxWidgets/Phoenix/issues/2225)，该方法可能会失败。

除了 `pip` 以外的安装方式都会额外支持任务栏的图标。 `pip` 不支持是因为 `pip`
只能把软件安装到类似 `/usr/lib/python3.X/site-packages`
的目录里，而软件的快捷方式、图标都必须放在该目录以外的其他目录。
当然，你手动完成也是可以的。

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

![icon](https://user-images.githubusercontent.com/32936898/224473440-2088edd7-42e5-45a3-a403-515e2daa019a.jpg)

## PPA

目前该软件还没有打包到 Ubuntu PPA 上。

这是一个临时的安装方法，它避开了 `wxpython` 的 bug（目前运行该网站的 Ubuntu
22.04 就是这样安装的）：

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

TODO

## brew

任何安装了 [`brew`](https://github.com/Homebrew/brew) 的系统均可：

- Any Linux distributions with linuxbrew
- macOS with homebrew

TODO

## Windows exe

下载 [exe 文件](https://github.com/nachifur/MulimgViewer/releases)：

- 安装版 `*_Setup.exe` （启动速度更快）
- 便携版 `*_Portable.exe`

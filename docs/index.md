---
hide-toc: true
---

# MulimgViewer 中文手册

[选择文档语言 · Choose your language](languages.md)

`````{container} manual-highlights

````{container} product-hero

```{container} manual-intro
**并行浏览，逐帧对比。**

在同一页对齐多个图像或视频来源，同步放大细节，将原图与算法结果一起导出。

[运行双视频示例](resources/usage.md)
```

```{figure} media/parallel-playback.gif
:alt: Cat 和 Sunset 并排翻页，右侧展开 Input & Playback。
:figclass: manual-figure

左格是 Cat，右格是 Sunset。单击下一页，两路同时前进一帧。
```
````

````{container} product-hero

```{container} manual-intro
**十张超 4K 图，只比同一处细节。**

在鸟头上画一次框，隐藏原图。十张 4608 × 2592 图像的同一块 160 × 160 像素区域并排铺开，沿鸟喙就能比较不同插值的边缘。

{ref}`跟做 1:1 对比 <native-detail>` [下载无损 PNG](media/sr-detail-native.png)
```

```{figure} media/walkthrough-sr-detail.gif
:alt: 在完整窗口内框选鸟头，切换到只显示十个原尺寸局部。
:figclass: manual-figure

跟随录屏设置放大框，再下载最终画布的 PNG，按 100% 查看边缘细节。
```
````

````{container} product-hero

```{container} manual-intro
**点一个位置，挑出一组样本。**

A、B 两个来源各占一行，每行显示三张。点中 B 行的第二张并保存，A 行的第二张也会一起导出。

{ref}`跟做并行挑图 <multi-source-picks>`
```

```{figure} media/walkthrough-parallel-picks.gif
:alt: 两行三列显示 A、B 的图像，点中下排中间一张，保存后重新打开两个来源的结果。
:figclass: manual-figure

Per source 设为 1,3。点中 B/02.png，按 Ctrl+S，再打开输出目录核对两张 02.png。
```
````
`````

```{container} demo-labels
- 关闭
- 试试同步翻帧
- 上一帧
- 下一帧
- Cat 与 Sunset 同步画面
- 试试并行挑图
- 点选任一文件，查看两个来源会一起保存哪一张。
- 将一起保存
- 功能亮点
- 恢复轮播
- 暂停轮播
```

```{container} manual-guides
- [下载与安装](resources/install.md) 选择系统对应的桌面包，或从源码安装
- [界面与快捷键](resources/interface.md) 从图标或菜单名查操作
- [右侧设置栏](resources/settings.md) 按分组查参数和生效方式
- [使用技巧](resources/large-images.md) 核对来源、视频时间与原尺寸细节
```

```{only} preview_manual
本页演示开发版功能。正在使用 3.9.7？请查看 [3.9.7 中文手册](https://mulimgviewer.readthedocs.io/zh-cn/docs-v3.9.7-r1/)。
```

```{only} not preview_manual
当前手册版本为 {sub-ref}`release`。[查看 3.9.7 中文手册](https://mulimgviewer.readthedocs.io/zh-cn/docs-v3.9.7-r1/)。
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: 安装与上手

resources/install
resources/usage
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: 操作参考

resources/interface
resources/settings
resources/large-images
```

```{toctree}
:hidden:
:caption: 开发与贡献

dev/dev
dev/localization
dev/release
misc/todo
```

```{toctree}
:hidden:
:caption: 版本与致谢

misc/changelog
misc/acknowledgements
```

```{toctree}
:hidden:
:caption: Languages

languages
```

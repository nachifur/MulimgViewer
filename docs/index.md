---
hide-toc: true
---

# MulimgViewer 中文手册

````{container} product-hero

```{container} manual-intro
**并行浏览，逐帧对比。**

在同一页对齐多个图像或视频来源，同步放大细节，将原图与算法结果一起导出。

[安装与自检](resources/install.md) [运行双视频示例](resources/usage.md)
```

```{figure} media/layout-window.png
:alt: 猫咪和海上日落并排显示，右侧展开布局参数。
:figclass: manual-figure

同一页上的两路视频。右侧的 Page 设为一行两列，Display scale 保持 1,1。
```
````

```{container} manual-guides
- [浏览与导出](resources/usage.md) 选择来源、对比细节和保存结果
- [右侧设置栏](resources/settings.md) 按界面分组查找参数与实例
- [开发指南](dev/dev.md) 添加算法、运行回归测试和提交修改
```

本手册对应当前源码版。使用已发布的安装包时，请选择对应版本的文档。

```{toctree}
:maxdepth: 2
:hidden:
:caption: 使用与开发

resources/install
resources/usage
resources/settings
dev/dev
```

```{toctree}
:hidden:
:caption: 项目记录

misc/changelog
misc/acknowledgements
misc/todo
```

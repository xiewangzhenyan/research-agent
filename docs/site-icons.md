# 网站图标

页面标识与浏览器图标统一来自 `frontend/src/components/brand/research-mark.tsx`。
修改后在 `frontend` 目录执行 `bun run generate:icons`，将生成的资源与
`src/lib/brand-assets.ts` 一起提交。

资源文件名包含 SVG 内容哈希，浏览器标签页、快捷方式、Apple 图标和应用清单
都引用对应版本。这样更换图形会产生新的地址，避免旧 `/icon` 一年缓存继续生效。
兼容入口 `/favicon.ico` 包含 16、32、48 像素图像，要求缓存重新验证；旧 `/icon`
与 `/apple-icon` 地址重定向至新资源。应用清单提供 192、512 像素及 maskable 图标。

发布验收应检查公网 HTML 中的实际链接、图像内容与尺寸、缓存响应头及
`/favicon.ico` 状态，不能只检查页内 SVG 标识。已经安装的桌面快捷方式何时更新
由浏览器或操作系统控制，可能需要重新添加。

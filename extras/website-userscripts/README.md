# 网站脚本说明

旧目录 `D:\Test\VSCode\temp` 中发现过网站 userscript 和翻译说明文件。它们不是视频相似检测、分类、重命名、转存主流程的一部分。

其中 userscript 文件含嵌入式第三方 API 凭据，因此本次没有直接复制到新项目。若以后确实需要纳入管理，建议先执行以下处理：

1. 轮换已经写入脚本的第三方 API 密钥。
2. 把密钥移到本地环境变量或单独的 ignored secrets 文件。
3. 只提交不含真实密钥的 `.example.user.js`。
4. 在 `.gitignore` 中继续忽略 `secrets/`、`.env` 和本地私有脚本。


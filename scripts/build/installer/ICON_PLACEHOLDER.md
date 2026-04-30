icon.ico (and icon.icns for Mac) must be added before the first release.

Generate from a 256x256 PNG via ImageMagick:

```
convert logo.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

For macOS (.icns):

```
mkdir logo.iconset
sips -z 16 16     logo.png --out logo.iconset/icon_16x16.png
sips -z 32 32     logo.png --out logo.iconset/icon_16x16@2x.png
sips -z 32 32     logo.png --out logo.iconset/icon_32x32.png
sips -z 64 64     logo.png --out logo.iconset/icon_32x32@2x.png
sips -z 128 128   logo.png --out logo.iconset/icon_128x128.png
sips -z 256 256   logo.png --out logo.iconset/icon_128x128@2x.png
sips -z 256 256   logo.png --out logo.iconset/icon_256x256.png
sips -z 512 512   logo.png --out logo.iconset/icon_256x256@2x.png
sips -z 512 512   logo.png --out logo.iconset/icon_512x512.png
iconutil -c icns logo.iconset -o icon.icns
```

Place the resulting icon.ico and icon.icns in this directory (scripts/build/installer/).

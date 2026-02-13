# Wallpaper app

Generate local wallpaper packs via ChoomLang + Automatic1111.

## Prerequisite

Start Automatic1111 with API enabled:

```bash
./webui.sh --api
```

Default A1111 endpoint used by `choom run` is:

- `http://127.0.0.1:7860`

## Run

Fast run:

```bash
choom run apps/wallpaper/scripts/pack_fast.choom --timeout 900
```

HD run:

```bash
choom run apps/wallpaper/scripts/pack_hd.choom --timeout 2400
```

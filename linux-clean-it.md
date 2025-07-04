# run it, clean it, do it.

```sh
sudo apt-get autoremove --purge -y \
  && sudo apt-get autoclean && sudo apt-get clean \
  && du -sh ~/.cache/* | sort -h \
  && rm -rf ~/.cache/*
```

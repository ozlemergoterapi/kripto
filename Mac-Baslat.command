#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

fail() {
  echo
  echo "$1"
  echo "Bu mesajı destek için paylaşabilirsiniz. Gerçek emir gönderilmedi."
  read -r -p "Pencereyi kapatmak için Enter... " _answer || true
  exit 1
}

echo "LSA Trader — Mac kurulumu / yalnızca simülasyon"
echo "Bu pencere açık kaldığı sürece bot çalışır. Durdurmak için Ctrl+C."

python_bin=""
for candidate in python3.13 python3.12 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;sys.exit(not ((3,12) <= sys.version_info[:2] < (3,14)))' 2>/dev/null; then
    python_bin="$candidate"
    break
  fi
done
if [ -z "$python_bin" ]; then
  fail "Python 3.12 veya 3.13 gerekli. python.org sitesinden macOS yükleyicisini kurup bu dosyayı yeniden açın."
fi

# Use a separate environment so a restored Linux venv is never reused on macOS.
"$python_bin" -m venv .venv-mac || fail "Yerel Python ortamı oluşturulamadı."
.venv-mac/bin/python -m pip install -r requirements.txt || fail "Bağımlılıklar kurulamadı. Yukarıdaki hata mesajını kontrol edin."

if ! .venv-mac/bin/python - <<'PY'
import socket
with socket.socket() as s:
    s.bind(('127.0.0.1', 8765))
PY
then
  fail "8765 portu kullanımda. LSA zaten açıksa mevcut pencereyi kullanın; ikinci bot başlatılmadı."
fi

echo "Panel açılıyor. Yeni işlemler panelde Başlat demenizi bekler."
(sleep 3; open 'http://127.0.0.1:8765') &
exec .venv-mac/bin/python -m lsa serve

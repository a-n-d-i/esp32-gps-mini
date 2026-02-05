./venv/bin/rshell -p /dev/ttyUSB0 -b 115200 --buffer-size 4096 rsync src/ /pyboard
./venv/bin/rshell -p /dev/ttyUSB0 repl
VERSION = 0.1

all: linux

release: linux win mac

linux:
	mkdir -p build/tmp
	cp kisstun.py build/kisstun-$(VERSION)-linux
	chmod a+x build/kisstun-$(VERSION)-linux

install: linux
	sudo install -m 755 build/kisstun-$(VERSION)-linux /usr/local/bin/kisstun

win:
	mkdir -p build/tmp
	curl -C - -L -o build/tmp/python-win.zip https://www.python.org/ftp/python/3.9.6/python-3.9.6-embed-amd64.zip
	curl -C - -L -o build/tmp/direwolf-win.zip https://github.com/wb2osz/direwolf/releases/download/1.8.1/direwolf-1.8.1-a231971_x86_64.zip
	curl -C - -L -o build/tmp/wintun.zip https://www.wintun.net/builds/wintun-0.14.1.zip
	unzip -j -o build/tmp/python-win.zip -d build/dist
	unzip -j -o build/tmp/direwolf-win.zip "*/direwolf.exe" -d build/dist
	unzip -j -o build/tmp/wintun.zip wintun/bin/amd64/wintun.dll -d build/dist
	cp kisstun.bat build/
	cp kisstun.py direwolf.conf build/dist/
	cd build && zip -r kisstun-$(VERSION)-win64.zip dist/ kisstun.bat
	rm -r build/kisstun.bat build/dist

mac:
	mkdir -p build/tmp
	touch build/a

clean:
	rm -rf build/


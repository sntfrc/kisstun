VERSION = 0.1

all: unix

release: unix win mac

unix:
	mkdir -p build/tmp
	cp kisstun.py build/kisstun-$(VERSION)
	chmod a+x build/kisstun-$(VERSION)

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
	rm -rf build/tmp/kissTUN.app build/tmp/mac
	mkdir -p build/tmp/mac
	osacompile -o build/tmp/mac/kissTUN.app kisstun.scpt
	mkdir -p build/tmp/mac/kissTUN.app/Contents/MacOS
	mkdir -p build/tmp/mac/kissTUN.app/Contents/Resources
	cp -a kisstun.py build/tmp/mac/kissTUN.app/Contents/Resources
	diskutil image create from --volumeName "kissTUN v$(VERSION)" --format UDZO build/tmp/mac build/kisstun-$(VERSION)-macos.dmg

clean:
	rm -rf build/


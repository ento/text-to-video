CODE_SRC = $(wildcard codes/*.txt codes/*.sh codes/*.sql codes/*.py codes/*.md codes/*.nix)
CODE_IMG = $(addsuffix .png,$(basename $(patsubst codes/%,images/%,$(CODE_SRC))))

all: script.csv final.ymmp

define CODE2IMG
python code2image.py $< $@
endef

images/%.png: codes/%.md code2image.py
	$(CODE2IMG)
images/%.png: codes/%.nix code2image.py
	$(CODE2IMG)
images/%.png: codes/%.py code2image.py
	$(CODE2IMG)
images/%.png: codes/%.sql code2image.py
	$(CODE2IMG)
images/%.png: codes/%.sh code2image.py
	$(CODE2IMG)
images/%.png: codes/%.txt code2image.py
	$(CODE2IMG)

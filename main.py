import csv
import subprocess
from functools import cached_property
import tempfile
import argparse
import hashlib
from pathlib import Path
import typing as t
from io import StringIO
from xml.sax import saxutils

from PIL import Image
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    ImageClip,
    TextClip,
    CompositeVideoClip,
    CompositeAudioClip,
)
from pydantic import BaseModel, Field, validator
import yaml

AUDIO_ROOT = Path(__file__).parent / "audio"
CODE_ROOT = Path(__file__).parent / "codes"
IMAGE_ROOT = Path(__file__).parent / "images"


class Anchors:
    width = 720
    height = 480

    @property
    def slide_height(self) -> int:
        return int(self.height * 0.8)

    @property
    def slide_width(self) -> int:
        return self.width - self.slide_left * 2

    @property
    def slide_left(self) -> int:
        return int(self.width * 0.05)

    @property
    def slide_top(self) -> int:
        return 0

    @property
    def caption_frame_top(self) -> int:
        return self.slide_height

    @property
    def caption_frame_left(self) -> int:
        return 0

    @property
    def caption_frame_height(self) -> int:
        return self.height - self.caption_frame_top

    @property
    def caption_frame_width(self) -> int:
        return self.width

    @property
    def caption_top(self) -> int:
        return self.slide_height + 10

    @property
    def caption_height(self) -> int:
        return self.caption_frame_height - 10 * 2

    @property
    def caption_left(self) -> int:
        return int(self.width * 0.1)

    @property
    def caption_width(self) -> int:
        return self.width - self.caption_left * 2

    @property
    def left_character_left(self) -> int:
        return 0

    @property
    def left_character_top(self) -> int:
        return self.slide_height - self.left_character_height

    @property
    def left_character_width(self) -> int:
        return self.left_character_height

    @property
    def left_character_height(self) -> int:
        return int(self.height * 0.2)


anchors = Anchors()


class VoiceOver(BaseModel):
    character: str
    voice: str
    text: str
    end_pause: str = "500ms"

    class Config:
        keep_untouched = (cached_property,)

    @validator("text")
    def validate_text(cls, value: str) -> str:
        return value.strip()

    @cached_property
    def clean_text(self) -> str:
        return self.text.replace("\n", " ")

    @cached_property
    def saml_text(self) -> str:
        escaped_text = saxutils.escape(self.clean_text)
        return f"<speak>{escaped_text}<break time='{self.end_pause}'/></speak>"

    def get_filepath(self, parent: Path) -> Path:
        return parent / f"{self.filename_base}.wav"

    def write_audio_request(self, writer, parent: Path) -> None:
        path = self.get_filepath(parent)
        if path.exists():
            return
        writer.writerow([self.filename_base, self.voice, self.saml_text])

    def as_audio_clip(self, parent) -> AudioFileClip:
        path = str(self.get_filepath(parent))
        print(path, self.saml_text)
        return AudioFileClip(path)

    def as_caption(self) -> TextClip:
        return TextClip(
            self.clean_text,
            color="white",
            font="Noto-Sans-Regular",
            fontsize=18,
            kerning=1,
            align="west",
            method="caption",
            size=(anchors.caption_width, anchors.caption_height),
        ).set_position((anchors.caption_left, anchors.caption_top))

    @cached_property
    def filename_base(self) -> str:
        m = hashlib.sha1()
        m.update(self.character.encode("utf8"))
        m.update(b"|")
        m.update(self.voice.encode("utf8"))
        m.update(b"|")
        m.update(self.saml_text.encode("utf8"))
        return m.hexdigest()


class SlideBase(BaseModel):
    voice_overs: t.List[VoiceOver] = Field(default_factory=list)
    min_duration: int = None

    def prepare(self) -> None:
        pass


class EmptySlide(SlideBase):
    def as_clip(self) -> None:
        return


class ImageSlide(SlideBase):
    image: str
    zoom: t.Optional[float] = None
    zoom_to_fit: bool = False

    def as_clip(self) -> ImageClip:
        return ImageSlide.fit(
            self.image,
            anchors.slide_left,
            anchors.slide_top,
            anchors.slide_width,
            anchors.slide_height,
            zoom_to_fit=self.zoom_to_fit,
            zoom=self.zoom,
        )

    @staticmethod
    def fit(
        image_path: str,
        frame_x: int,
        frame_y,
        frame_width: int,
        frame_height: int,
        zoom_to_fit: bool = False,
        zoom: float = None,
    ) -> ImageClip:
        image = Image.open(Path(image_path).resolve())
        image_width, image_height = image.size

        # Fixed zoom?
        if zoom is not None:
            width = image_width * zoom
            height = image_height * zoom
        # Image is bigger that the frame width?
        elif image_width > frame_width or image_height > frame_height:
            if image_width / frame_width > image_height / frame_height:
                # zoom out by the bigger ratio to scale
                width = frame_width
                height = width * image_height / image_width
            else:
                height = frame_height
                width = height * image_width / image_height
        # Image is smaller that the frame width - enlarge it?
        elif zoom_to_fit:
            if image_width / frame_width > image_height / frame_height:
                # zoom in by the smaller ratio to scale
                height = frame_height
                width = height * image_width / image_height
            else:
                width = frame_width
                height = width * image_height / image_width
        else:
            width = image_width
            height = image_height

        x = frame_x + (frame_width - width) * 0.5
        y = frame_y + (frame_height - height) * 0.5

        return ImageClip(image_path).resize((width, height)).set_position((x, y))


class CodeSlide(SlideBase):
    code: str
    ext: str

    class Config:
        keep_untouched = (cached_property,)

    def as_clip(self) -> ImageClip:
        image_path = IMAGE_ROOT / f"{self.filename_base}.png"
        return ImageSlide(image=str(image_path)).as_clip()

    def prepare(self) -> None:
        path = self.get_filepath(CODE_ROOT)
        if path.is_file():
            return
        path.write_text(self.code)

    def get_filepath(self, parent: Path) -> Path:
        return parent / f"{self.filename_base}.{self.ext}"

    @cached_property
    def filename_base(self) -> str:
        m = hashlib.sha1()
        m.update(self.ext.encode("utf8"))
        m.update(b"|")
        m.update(self.code.encode("utf8"))
        return m.hexdigest()


class TextSlide(SlideBase):
    text: str
    font_size: float = 25

    def as_clip(self) -> TextClip:
        return TextClip(
            self.text,
            color="black",
            bg_color="white",
            font="Noto-Sans-Regular",
            kerning=1,
            fontsize=self.font_size,
            method="caption",
            align="west",
            size=(anchors.slide_width, anchors.slide_height),
        ).set_position((anchors.slide_left, anchors.slide_top))


class Character(BaseModel):
    image: str
    voice: str  # mimic3 voice name


class Script(BaseModel):
    slides: t.List[dict] = Field(default_factory=list)
    characters: t.Dict[str, Character] = Field(default_factory=dict)

    def parse_slides(self) -> t.List[SlideBase]:
        current_item = EmptySlide()
        slides = [current_item]
        # A slide may have multiple VOs.
        # A VO belongs to only one slide.
        # A slide's duration is the sum of all VOs' durations.
        for item in self.slides:
            if "image" in item:
                current_item = ImageSlide.parse_obj(item)
                slides.append(current_item)
                continue
            if "text" in item:
                current_item = TextSlide.parse_obj(item)
                slides.append(current_item)
                continue
            if "code" in item:
                current_item = CodeSlide.parse_obj(item)
                slides.append(current_item)
                continue
            key, value = list(item.items())[0]
            current_item.voice_overs.append(
                VoiceOver(character=key, text=value, voice=self.characters[key].voice)
            )

        return slides


def main(yaml_path: Path, output_path: Path):
    video_clips = []
    audio_clips = []
    script = Script.parse_obj(yaml.safe_load(yaml_path.read_text()))
    slides = script.parse_slides()
    last_clip_end = 0
    generate_audio(slides)
    for slide in slides:
        slide.prepare()
    subprocess.run(["make"], check=True)
    for slide in slides:
        slide_duration = 0
        caption_start = last_clip_end
        for voice_over in slide.voice_overs:
            audio_clip = voice_over.as_audio_clip(AUDIO_ROOT)
            voice_over_duration = audio_clip.duration

            audio_clips.append(audio_clip.set_start(caption_start))

            caption_clip = (
                voice_over.as_caption()
                .set_start(caption_start)
                .set_duration(voice_over_duration)
            )
            video_clips.append(caption_clip)

            slide_duration += voice_over_duration
            caption_start += voice_over_duration

        if slide.min_duration is not None and slide_duration < slide.min_duration:
            slide_duration = slide.min_duration

        maybe_slide_clip = slide.as_clip()
        if maybe_slide_clip:
            slide_clip = maybe_slide_clip.set_duration(slide_duration).set_start(
                last_clip_end
            )
            video_clips.append(slide_clip)
        last_clip_end += slide_duration

    screen_size = (anchors.width, anchors.height)

    # add static images
    video_clips.insert(
        0,
        ColorClip(
            color=(0, 0, 0),
            size=(anchors.caption_frame_width, anchors.caption_frame_height),
        )
        .set_position((anchors.caption_frame_left, anchors.caption_frame_top))
        .set_duration(last_clip_end),
    )
    for character in script.characters.values():
        video_clips.append(
            ImageSlide.fit(
                character.image,
                anchors.left_character_left,
                anchors.left_character_top,
                anchors.left_character_width,
                anchors.left_character_height,
            ).set_duration(last_clip_end)
        )

    audio_track = CompositeAudioClip(audio_clips)
    cvc = CompositeVideoClip(
        video_clips,
        size=screen_size,
        bg_color=(255, 255, 255),
    )
    cvc.audio = audio_track
    cvc.set_duration(last_clip_end).write_videofile(
        str(output_path),
        fps=30,
    )


def generate_audio(slides: t.List[SlideBase]) -> None:
    """
    Once this call succeeds, all voice over objects should have
    corresponding audio files generated.
    """
    if not AUDIO_ROOT.exists():
        AUDIO_ROOT.mkdir(parents=True)
    out = StringIO()
    writer = csv.writer(out, delimiter="|")
    for slide in slides:
        for voice_over in slide.voice_overs:
            voice_over.write_audio_request(writer, AUDIO_ROOT)
    audio_requests = out.getvalue()
    if not audio_requests:
        return
    print("generating audio")
    print(audio_requests)
    subprocess.run(
        [
            "mimic3",
            "--remote",
            "--ssml",
            "--stdin-format",
            "lines",
            "--csv-voice",
            "--length-scale",
            "1.1",
            "--output-dir",
            AUDIO_ROOT,
        ],
        text=True,
        input=audio_requests,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_yaml", type=Path)
    parser.add_argument("output_path", type=Path)
    args = parser.parse_args()
    main(args.source_yaml, args.output_path)

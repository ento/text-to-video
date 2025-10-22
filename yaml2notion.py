import argparse
import json
import logging
import os
import sys
import typing as t
from pathlib import Path

logging.basicConfig(level=logging.INFO)

import notional
from notional import blocks, types

from project import Item, Project, VoiceItem


def main(ymmp_path: Path, notion_page_id: str, auth_token: str):
    notion = notional.connect(auth=auth_token)
    page = notion.pages.retrieve(notion_page_id)
    project = Project.parse_obj(json.loads(ymmp_path.read_text(encoding="utf-8-sig")))
    characters = {
        c.Name: Path(c.TachieDefaultItemParameter.DefaultFace)
        for c in project.Characters
    }

    children = []
    count = 0
    for item in project.Timeline.Items:
        block = item_to_notion_block(item, characters)
        if block:

            children.append(block)
            count += 1
        if count > 3:
            break

    notion.blocks.children.append(page, *children)


from pydantic.fields import ModelField


def add_fields(cls, **field_definitions: t.Any):
    new_fields: t.Dict[str, t.ModelField] = {}
    new_annotations: t.Dict[str, t.Optional[type]] = {}

    for f_name, f_def in field_definitions.items():
        if isinstance(f_def, tuple):
            try:
                f_annotation, f_value = f_def
            except ValueError as e:
                raise Exception(
                    "field definitions should either be a tuple of (<type>, <default>) or just a "
                    "default value, unfortunately this means tuples as "
                    "default values are not allowed"
                ) from e
        else:
            f_annotation, f_value = None, f_def

        if f_annotation:
            new_annotations[f_name] = f_annotation

        new_fields[f_name] = ModelField.infer(
            name=f_name,
            value=f_value,
            annotation=f_annotation,
            class_validators=None,
            config=cls.__config__,
        )

    cls.__fields__.update(new_fields)
    cls.__annotations__.update(new_annotations)


add_fields(blocks.ColumnList._NestedData, children=(t.List[blocks.Column], ...))
add_fields(blocks.Column._NestedData, children=(t.List[blocks.Block], ...))


def item_to_notion_block(
    item: Item, characters: t.Dict[str, Path]
) -> t.Optional[blocks.Block]:
    if isinstance(item, VoiceItem):
        character_file = types.ExternalFile[characters[item.CharacterName]]
        tachie = blocks.Image(image=character_file)
        children = [
            blocks.Column(column=dict(children=[tachie, blocks.Paragraph[item.Serif]]))
        ]
        if item.CharacterName == "Red Parrot":
            children.insert(
                0, blocks.Column(column=dict(children=[blocks.Paragraph[""]]))
            )
        else:
            children.append(blocks.Column(column=dict(children=[blocks.Paragraph[""]])))
        column_list = blocks.ColumnList(column_list={"children": children})
        return column_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ymmp_path", type=Path)
    parser.add_argument("notion_page_id")
    args = parser.parse_args()
    auth_token = os.getenv("NOTION_AUTH_TOKEN")
    main(args.ymmp_path, args.notion_page_id, auth_token)

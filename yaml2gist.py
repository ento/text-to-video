import argparse
import json
import logging
import os
import shutil
import sys
import typing as t
from pathlib import Path, PureWindowsPath

import git
from github import Github, InputFileContent
from PIL import Image
from pydantic import BaseModel

from project import ImageItem, Item, Project, TextItem, VoiceItem


class GistRepo(BaseModel):
    path: Path
    gist_id: t.Optional[str]
    repo: t.Optional[git.Repo] = None

    class Config:
        arbitrary_types_allowed = True

    @property
    def git_push_url(self):
        assert self.gist_id is not None
        return f"git@github.com:{self.gist_id}.git"

    def init(self, github: Github):
        if (self.path / ".git").is_dir():
            self.repo = git.Repo(self.path)
            if self.gist_id:
                assert self.repo.remotes.origin.url == self.git_push_url
            else:
                repo_name = self.repo.remotes.origin.url.split(":")[1]
                self.gist_id = repo_name.split(".")[0]
        elif self.gist_id:
            self.repo = git.Repo.clone_from(self.git_push_url, self.path)
        else:
            user = github.get_user()
            gist = user.create_gist(
                public=False,
                files={".gitkeep": InputFileContent(".gitkeep")},
                description="ymm export",
            )
            self.gist_id = gist.id
            self.repo = git.Repo.clone_from(self.git_push_url, self.path)
        for child in self.path.glob("*"):
            if child.name == ".git":
                continue
            if child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)

    def copy_file(self, path: Path):
        flat_path = self.path / self.flatten_path(path)
        flat_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, flat_path)

    def write_file(self, path: Path, content: str):
        flat_path = self.path / self.flatten_path(path)
        flat_path.parent.mkdir(parents=True, exist_ok=True)
        flat_path.write_text(content)

    def flatten_path(self, path: Path) -> Path:
        return Path(str(path).replace("/", "_"))

    def url_for(self, path: Path, user: str) -> Path:
        flat_path = self.flatten_path(path)
        return f"https://gist.githubusercontent.com/{user}/{self.gist_id}/raw/{self.repo.head.commit}/{flat_path}"

    def commit_and_push(self):
        if len(self.repo.index.diff(None)) == 0:
            return
        self.repo.git.add(all=True)
        author = git.Actor("Alice Author", "alice@authors.tld")
        committer = git.Actor("Cecil Committer", "cecil@committers.tld")
        message = "Initial commit"
        self.repo.index.commit(message, author=author, committer=committer)
        self.repo.remotes.origin.push(refspec="main:main")


def main(
    ymmp_path: Path,
    github: Github,
    index_gist_id: t.Optional[str],
    assets_gist_id: t.Optional[str],
):
    project = Project.parse_obj(json.loads(ymmp_path.read_text(encoding="utf-8-sig")))

    assets_repo = export_assets_repo(project, github, assets_gist_id)
    export_main_repo(project, github, index_gist_id, assets_repo)


def export_main_repo(
    project: Project, github: Github, gist_id: str, assets_repo: GistRepo
) -> GistRepo:
    markdown = write_index_page(project, github, assets_repo)

    repo = GistRepo(path=Path("export/index_repo"), gist_id=gist_id)
    repo.init(github)
    repo.write_file("README.md", markdown)
    repo.commit_and_push()
    return repo


def write_index_page(project: Project, github: Github, assets_repo: GistRepo) -> str:
    characters = {
        c.Name: format_image_path(c.TachieDefaultItemParameter.DefaultFace)
        for c in project.Characters
    }
    github_login = github.get_user().login
    markdown = []
    last_character = None
    items = sorted(
        filter(
            lambda item: isinstance(item, (VoiceItem, ImageItem, TextItem)),
            project.Timeline.Items,
        ),
        key=lambda item: (item.Frame, 1 if isinstance(item, ImageItem) else 0),
    )
    for item in items:
        if isinstance(item, VoiceItem):
            if last_character is None or last_character != item.CharacterName:
                if last_character is not None:
                    markdown.append("</p>")
                markdown.append("<p>")
                avatar_url = assets_repo.url_for(
                    characters[item.CharacterName], github_login
                )
                markdown.append(f'<img src="{avatar_url}" width="18px" />')
                last_character = item.CharacterName
            markdown.append(item.Serif.replace("\n", " "))
        if isinstance(item, ImageItem):
            if last_character is not None:
                markdown.append("</p>")
                last_character = None
            height_attr = format_image_height(item.FilePath)
            image_url = assets_repo.url_for(
                format_image_path(item.FilePath), github_login
            )
            markdown.append(f"<p align=center><img src={image_url} {height_attr}/></p>")
        if isinstance(item, TextItem):
            if last_character is not None:
                markdown.append("</p>")
                last_character = None
            markdown.append("<blockquote>")
            markdown.append(item.Text)
            markdown.append("</blockquote>")
    if last_character is not None:
        markdown.append("</p>")
    return "\n".join(markdown)


def export_assets_repo(project: Project, github: Github, gist_id: str) -> GistRepo:
    repo = GistRepo(path=Path("export/assets_repo"), gist_id=gist_id)
    repo.init(github)
    for c in project.Characters:
        repo.copy_file(format_image_path(c.TachieDefaultItemParameter.DefaultFace))
    for item in project.Timeline.Items:
        if isinstance(item, ImageItem):
            repo.copy_file(format_image_path(item.FilePath))
    repo.commit_and_push()
    return repo


def format_image_path(raw_path: str) -> Path:
    return Path(PureWindowsPath(raw_path))


def format_image_height(raw_path: str) -> Path:
    image = Image.open(format_image_path(raw_path))
    _image_width, image_height = image.size
    if image_height > 300:
        return 'height="300px"'
    return ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ymmp_path", type=Path)
    parser.add_argument("--index-gist-id", required=False)
    parser.add_argument("--assets-gist-id", required=False)
    args = parser.parse_args()
    github_token = os.getenv("GITHUB_TOKEN")
    github = Github(github_token)
    main(args.ymmp_path, github, args.index_gist_id, args.assets_gist_id)

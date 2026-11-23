# bbdc-to-ai

- The workspace also contains files outside bbdc-to-ai. Restrict edits and commits to project files and review the staged paths before committing.
- Keep `config.yaml`, virtual environments, Android captures, account data, databases, generated reviews, private reports, and APKs local. Ship only `config.example.yaml` as the default configuration.
- For feature updates and bug fixes, run `python -m unittest discover -s tests`, document user-visible changes, commit the tested changes, and push them to the GitHub repository. Keep related changes in one focused commit.
- When publishing a new Windows executable, record the changes in `CHANGELOG.md`, build and test the executable, and publish the matching version tag and release.

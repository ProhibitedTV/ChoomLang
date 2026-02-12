# Release Steps

1. Run tests
   - `pytest`
2. Build distribution artifacts
   - `python -m build`
3. Commit and tag
   - `git commit -m "Release v0.8.0"`
   - `git tag -a v0.8.0 -m "ChoomLang v0.8.0"`
4. Push branch and tag
   - `git push`
   - `git push origin v0.8.0`
5. Create GitHub release notes manually
   - Use `CHANGELOG.md` 0.8.0 bullets as the basis
   - Include key commands (`choom profile`, `choom lint`, `choom run`)

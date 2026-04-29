import os
import subprocess


def git_commit_and_push(repo_dir: str, files: list, message: str):
    env = {**os.environ}

    def run(cmd):
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            print(f"[WARN] git 명령 실패: {' '.join(cmd)}\n{result.stderr}")
        return result

    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])
    for f in files:
        run(["git", "add", f])
    result = run(["git", "commit", "-m", message])
    if "nothing to commit" in result.stdout + result.stderr:
        print("[INFO] registry 변경 없음 — 커밋 스킵")
        return
    push = run(["git", "push"])
    if push.returncode != 0:
        print(f"[ERROR] registry push 실패: {push.stderr}", file=__import__("sys").stderr)
        __import__("sys").exit(1)
    print("[INFO] registry 커밋 완료")

# ⚠️ 确保你当前在 clean-main 或其它目标分支上
$commits = Get-Content keep_commits.txt
foreach ($commit in $commits) {
    # 检查是否当前分支已包含该提交
    $exists = git branch --contains $commit | Where-Object { $_ -match "^\*" }
    if ($exists) {
        Write-Host "✅ 跳过已合并提交 $commit"
        continue
    }

    Write-Host "尝试 cherry-pick 提交 $commit ..."
    git cherry-pick $commit
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "❗️ 冲突发生！请手动解决冲突后，执行："
        Write-Host "    git add <解决的文件>"
        Write-Host "    git cherry-pick --continue"
        Write-Host "完成后，再次粘贴此命令继续后续提交。"
        break
    }
}
Write-Host "所有提交已尝试合并完成（或在冲突处停止）"

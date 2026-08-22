# RSS → Discord

`feeds.csv` に登録した RSS / Atom フィードを GitHub Actions が 15 分ごとに確認し、新着記事だけを Discord Webhook へ送信します。通知済みの記事 ID は `data/seen_items.json` に記録され、ワークフローが自動でコミットします。

## 初期設定

1. Discord のチャンネル設定から Webhook を作成し、その URL をコピーします。
2. GitHub リポジトリの **Settings → Secrets and variables → Actions** で、Repository secret `DISCORD_WEBHOOK_URL` を作成して URL を登録します。
3. `feeds.csv` にフィードを追加します。列名は必ず `name,url` にしてください。

```csv
name,url
OpenAI Blog,https://openai.com/news/rss.xml
Example Blog,https://example.com/feed.xml
```

4. 変更を main ブランチへ push します。初回は Actions の **RSS to Discord** を開き、**Run workflow** から「既存記事を通知せず、通知済みとして初期化する」を有効にして実行してください。

以後は新着記事だけが投稿されます。Webhook の疎通確認は、手動実行時に「各フィードの最新記事をテスト送信する」を有効にしてください。このテストは通知済み状態を変更しません。

## 注意点

- GitHub Actions のスケジュール実行は混雑時に遅れることがあります。
- Actions が状態ファイルを push できるよう、リポジトリの Actions permissions で **Read and write permissions** を許可してください。
- GitHub の既定ブランチで 60 日間アクティビティがない場合、schedule ワークフローが自動停止することがあります。必要に応じて手動実行または定期的な更新をしてください。

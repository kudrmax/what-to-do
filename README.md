# Чем заняться

Локальное приложение: собирает анонсы мероприятий из публичных Telegram-каналов, Claude превращает посты в карточки событий и склеивает дубли.

## Бэкенд

```bash
uv sync
uv run where-to-go            # API на http://127.0.0.1:18765, описание ручек на /docs, данные в ~/Library/Application Support/where-to-go
uv run pytest
```

Claude вызывается через `claude-agent-sdk`, то есть через вход в Claude Code: нужен установленный и залогиненный `claude`.

Пайплайн: `telegram` (сбор постов с t.me/s/<канал>) → `extraction` (Claude: пост → события и места) → `linking` + `matching` (склейка дублей, переносы и отмены) → `resolution` (поля карточки из всех источников, конфликты) → `feed` (лента по дням) → `api`.

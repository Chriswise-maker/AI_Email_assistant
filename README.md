# AI Email Assistant

An intelligent email triage system powered by multiple LLM providers (Groq, DeepSeek, Gemini, Claude) that automatically categorizes, prioritizes, and summarizes incoming emails.

## Features

- **Multi-Provider LLM Support**: Choose between Groq, DeepSeek, Google Gemini, or Anthropic Claude
- **Automatic Email Categorization**: Intelligently sorts emails into categories (Security, Bills, Orders, Newsletters, Personal, Notifications, Spam, Other)
- **Priority Scoring**: Assigns priority levels from 1-5 to help you focus on what matters
- **Multilingual Summaries**: Preserves the original language of emails in summaries
- **Rule-Based Actions**: Automatically flags, marks as read, or applies custom actions based on categories
- **IMAP Support**: Works with any IMAP-compliant email provider

## Quick Start

### Prerequisites

- Python 3.11+
- An IMAP email account (Gmail, GMX, etc.)
- API key for at least one LLM provider (Groq, DeepSeek, Gemini, or Claude)

### Installation

1. **Clone the repository**
   ```bash
   cd /path/to/AI_Email_assistant
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Create a `.env` file based on `.env.example`:
   ```bash
   cp .env.example .env
   ```
   
   Add your credentials:
   ```
   # LLM Provider API Keys (at least one required)
   GROQ_API_KEY=your_groq_key_here
   ANTHROPIC_API_KEY=your_claude_key_here
   GEMINI_API_KEY=your_gemini_key_here
   
   # Email Account Passwords
   PASSWORD_GMX=your_email_password_here
   ```

4. **Configure email accounts**
   
   Edit `config.yaml` to add your email accounts:
   ```yaml
   accounts:
     - id: GMX
       email: your.email@gmx.net
       server: imap.gmx.net
       enabled: true
       provider: imap
   ```

## Configuration

### LLM Providers

Configure providers in `config.yaml`:

```yaml
providers:
  claude:
    api_key_env: ANTHROPIC_API_KEY
    model: claude-sonnet-4-5
    thinking_level: medium  # low, medium, high
  
  gemini:
    api_key_env: GEMINI_API_KEY
    model: gemini-3-flash-preview
    thinking_level: low
  
  groq:
    api_key_env: GROQ_API_KEY
    model: llama-3.3-70b-versatile

settings:
  provider: claude  # Choose your active provider
  dry_run: false    # Set true to test without applying actions
  max_body_chars: 3000
```

### Categories and Rules

Customize how emails are categorized and what actions to take:

```yaml
categories:
  - Security
  - Bills & Invoices
  - Orders & Shipping
  - Newsletters
  - Personal
  - Notifications
  - Spam
  - Other

rules:
  Security: flag
  Bills & Invoices: flag
  Orders & Shipping: no_action
  Newsletters: mark_read
  Personal: no_action
  Notifications: no_action
  Spam: mark_read
  Other: no_action
```

## How It Works

1. **Connect**: The system connects to configured IMAP accounts
2. **Fetch**: Retrieves all unread emails from the Inbox
3. **Analyze**: Sends email content to the selected LLM for categorization
4. **Categorize**: AI returns category, priority, and summary in JSON format
5. **Apply Rules**: Executes configured actions (flag, mark read, etc.)
6. **Mark Processed**: Marks emails as read to prevent re-processing

## Troubleshooting

### "Analysis Failed" Errors

- **Quota Exceeded**: Switch to a different provider or wait for quota reset
- **Invalid API Key**: Verify your API keys in `.env`
- **Network Issues**: Check your internet connection

### Emails Being Re-Processed

- The system marks emails as "seen" after processing
- If you manually mark emails as unread, they will be re-processed

### Gemini Rate Limits

Gemini's free tier has strict quotas (20 requests/day for some models). Consider:
- Switching to Claude or Groq (higher limits)
- Upgrading your Gemini API plan
- Processing emails in smaller batches

## File Structure

```
AI_Email_assistant/
├── backend.py             # Email processing logic
├── llm_providers.py       # LLM provider implementations
├── database.py            # SQLite persistence layer
├── utils.py               # Helper functions
├── config.yaml            # Main configuration
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not tracked)
└── .env.example           # Template for .env
```

## API Provider Information

### Groq
- **Fast inference** with open-source models
- **Model**: `llama-3.3-70b-versatile`

### Anthropic Claude
- **High-quality reasoning** with extended thinking mode
- **Models**: `claude-sonnet-4-5`, `claude-opus-4-6`

### Google Gemini
- **Models**: `gemini-3-flash-preview`, `gemini-3-pro-preview`
- **Rate Limits**: Free tier has daily quotas

### DeepSeek
- **Cost-effective** Chinese LLM provider
- **Model**: `deepseek-chat`

## Advanced Configuration

### Thinking Level (Gemini/Claude)

The `thinking_level` parameter controls reasoning depth:
- **low**: Fast, suitable for simple categorization
- **medium**: Balanced performance and quality
- **high**: Maximum reasoning, slower but more accurate

### Dry Run Mode

Enable `dry_run: true` in `config.yaml` to test email processing without actually modifying emails:
```yaml
settings:
  dry_run: true
```

## License

MIT License - feel free to use and modify as needed.

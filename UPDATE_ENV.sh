#!/bin/bash
# Helper script to update .env with new API keys
# Run this after rotating your keys

echo "🔐 DreamDive API Key Update Helper"
echo "=================================="
echo ""
echo "This script will help you update your .env file with NEW rotated keys."
echo "Make sure you've rotated ALL keys before continuing!"
echo ""
read -p "Have you rotated all 4 API keys? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Please rotate your keys first, then run this script again."
    exit 1
fi

echo ""
echo "Enter your NEW API keys:"
echo ""

read -p "Moonshot API Key: " moonshot_key
read -p "Gemini API Key: " gemini_key
read -p "OpenAI API Key: " openai_key
read -p "Qwen API Key: " qwen_key

cat > .env << EOF
# Runtime LLM configuration.

DREAMDIVE_LLM_PROVIDER_ORDER='["qwen", "gemini", "moonshot", "openai"]'

DREAMDIVE_LLM_MOONSHOT_API_KEY="$moonshot_key"
DREAMDIVE_LLM_MOONSHOT_BASE_URL="https://api.moonshot.ai/v1"
DREAMDIVE_LLM_MOONSHOT_MODEL="kimi-k2.5"

DREAMDIVE_LLM_GEMINI_API_KEY="$gemini_key"
DREAMDIVE_LLM_GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
DREAMDIVE_LLM_GEMINI_MODEL="gemini-2.5-flash"

DREAMDIVE_LLM_OPENAI_API_KEY="$openai_key"
DREAMDIVE_LLM_OPENAI_BASE_URL="https://api.openai.com/v1"
DREAMDIVE_LLM_OPENAI_MODEL="gpt-4o"

DREAMDIVE_LLM_QWEN_API_KEY="$qwen_key"
DREAMDIVE_LLM_QWEN_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DREAMDIVE_LLM_QWEN_MODEL="qwen3.5-flash"

# Optional runtime settings
# DREAMDIVE_PERSISTENCE_BACKEND="session"
# DREAMDIVE_DATABASE_URL="postgresql+psycopg://dreamdive:dreamdive@localhost:5432/dreamdive"
EOF

echo ""
echo "✅ .env file updated successfully!"
echo ""
echo "Testing configuration..."
PYTHONPATH=src python3 -c "from dreamdive.config import get_settings; s = get_settings(); print(f'✓ Loaded {len(s.llm_profiles())} LLM profiles')" 2>/dev/null && echo "✓ Configuration valid!" || echo "⚠️  Configuration has errors"

echo ""
echo "🎉 Done! Your API keys are now secured."
echo ""
echo "Next steps:"
echo "1. Verify old keys are deleted from provider dashboards"
echo "2. Test with: PYTHONPATH=src python3 -m dreamdive.cli run --help"
echo "3. Delete SECURITY_ALERT.md and this script: rm SECURITY_ALERT.md UPDATE_ENV.sh"
EOF

chmod +x UPDATE_ENV.sh

#!/bin/bash
# scripts/stack_control.sh
# Uso desde fish: bash scripts/stack_control.sh on|off|status

case "$1" in
  on)
    sed -i '' 's/AI_STACK_ENABLED=.*/AI_STACK_ENABLED=true/' .env
    echo "✅ AI Stack ACTIVADO — toda implementación pasa por miaamia-dev"
    ;;
  off)
    sed -i '' 's/AI_STACK_ENABLED=.*/AI_STACK_ENABLED=false/' .env
    echo "🔓 AI Stack DESACTIVADO — modo libre para asistentes externos"
    ;;
  status)
    val=$(grep "AI_STACK_ENABLED" .env | cut -d= -f2)
    if [ "$val" = "true" ]; then
      echo "✅ AI Stack ACTIVO (AI_STACK_ENABLED=true)"
    else
      echo "🔓 AI Stack DESACTIVADO (AI_STACK_ENABLED=false)"
    fi
    ;;
  *)
    echo "Uso: bash scripts/stack_control.sh on|off|status"
    ;;
esac

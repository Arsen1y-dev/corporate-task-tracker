#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON="${PYTHON:-python3}"
if [ -f "$DIR/.venv/bin/python" ]; then
  PYTHON="$DIR/.venv/bin/python"
fi

mkdir -p "$DIR/proto/generated"
"$PYTHON" -m grpc_tools.protoc -I"$DIR/proto" --python_out="$DIR/proto/generated" --grpc_python_out="$DIR/proto/generated" "$DIR/proto/auth.proto"
touch "$DIR/proto/generated/__init__.py"

python3 -c "
with open('$DIR/proto/generated/auth_pb2_grpc.py', 'r') as f:
    c = f.read()
c = c.replace('import auth_pb2 as auth__pb2', 'try:\n    import auth_pb2 as auth__pb2\nexcept ImportError:\n    from . import auth_pb2 as auth__pb2')
with open('$DIR/proto/generated/auth_pb2_grpc.py', 'w') as f:
    f.write(c)
"

# Also copy into services for self-contained packages
for svc in auth-service tracker-service; do
  mkdir -p "$DIR/services/$svc/src/proto"
  cp "$DIR/proto/generated/"*.py "$DIR/services/$svc/src/proto/"
  touch "$DIR/services/$svc/src/proto/__init__.py"
done

echo "Proto stubs generated and synced."

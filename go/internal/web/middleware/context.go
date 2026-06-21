package middleware

import (
	"context"

	"github.com/lwhx/zhuimange/internal/auth"
)

type sessionCtxKey struct{}

// WithSession 将会话存入 context。
func WithSession(ctx context.Context, s *auth.SessionData) context.Context {
	return context.WithValue(ctx, sessionCtxKey{}, s)
}

// SessionFromContext 从 context 取出会话（可能为 nil）。
func SessionFromContext(ctx context.Context) *auth.SessionData {
	if s, ok := ctx.Value(sessionCtxKey{}).(*auth.SessionData); ok {
		return s
	}
	return nil
}

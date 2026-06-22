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

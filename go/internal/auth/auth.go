// Package auth 实现密码哈希、会话管理与 CSRF 防护。
//
// 会话采用自签 cookie（HMAC-SHA256），值含登录时间，无需服务端 session 存储。
// 与 Python 版 Flask session 语义一致：cookie 签名 + 过期判断。
package auth

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"golang.org/x/crypto/bcrypt"

	"github.com/lwhx/zhuimange/internal/store"
)

var (
	// ErrNotAuthenticated 会话未认证或已过期
	ErrNotAuthenticated = errors.New("未登录或会话已过期")
	// ErrInvalidCookie cookie 格式非法或签名不匹配
	ErrInvalidCookie = errors.New("无效的会话 cookie")
)

// sessionCookieName 会话 cookie 名称。
const sessionCookieName = "zmg_session"

// SessionData 会话数据（编码进 cookie）。
type SessionData struct {
	Authenticated bool      `json:"auth"`
	LoginTime     time.Time `json:"login_at"`
	Version       int       `json:"ver,omitempty"` // session 版本号，改密码后递增使旧 session 失效
}

// Authenticator 处理密码哈希与会话签发。
type Authenticator struct {
	store       *store.Store
	secretKey   []byte
	sessionDays int
	// sessionVersion 用于改密码后失效旧 session：存 DB，每次校验比对。
}

// New 创建认证器。
func New(s *store.Store, secretKey string, sessionDays int) *Authenticator {
	return &Authenticator{
		store:       s,
		secretKey:   []byte(secretKey),
		sessionDays: sessionDays,
	}
}

// isSecureRequest 判断请求是否通过 HTTPS（用于设置 cookie 的 Secure 标志）。
func isSecureRequest(r *http.Request) bool {
	if r.TLS != nil {
		return true
	}
	// 支持反向代理（Nginx/Caddy 等）
	if proto := r.Header.Get("X-Forwarded-Proto"); proto == "https" {
		return true
	}
	return false
}

// HashPassword 用 bcrypt 哈希密码（cost=12，与 Python 版一致）。
func HashPassword(password string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), 12)
	return string(bytes), err
}

// CheckPassword 校验密码。
// 兼容 Python 版 bcrypt（$2b$/$2a$），bcrypt.CompareHashAndPassword 自动处理。
func CheckPassword(password, hash string) bool {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(password)) == nil
}

// IsBcryptHash 判断是否为 bcrypt 哈希格式。
func IsBcryptHash(s string) bool {
	return strings.HasPrefix(s, "$2a$") || strings.HasPrefix(s, "$2b$") || strings.HasPrefix(s, "$2y$")
}

// Login 校验密码并签发会话 cookie。
// 返回错误表示密码错误或系统异常。r 用于判断是否 HTTPS（设置 Secure 标志）。
func (a *Authenticator) Login(ctx context.Context, w http.ResponseWriter, r *http.Request, password string) error {
	hash, err := a.store.GetSetting(ctx, "auth_password", "")
	if err != nil {
		return fmt.Errorf("读取密码设置失败: %w", err)
	}
	if hash == "" {
		return errors.New("系统未设置访问密码")
	}
	if !CheckPassword(password, hash) {
		return errors.New("密码错误")
	}

	// 读取当前 session version（用于改密码后失效旧 session）
	versionStr, _ := a.store.GetSetting(ctx, "session_version", "0")
	version, _ := strconv.Atoi(versionStr)

	// 签发会话
	data := SessionData{
		Authenticated: true,
		LoginTime:     time.Now(),
		Version:       version,
	}
	return a.setSession(w, r, data)
}

// Logout 清除会话 cookie。r 用于判断是否 HTTPS。
func (a *Authenticator) Logout(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		HttpOnly: true,
		Secure:   isSecureRequest(r),
		SameSite: http.SameSiteLaxMode,
	})
}

// setSession 编码会话数据并用 HMAC 签名，写入 cookie。r 用于判断是否 HTTPS。
func (a *Authenticator) setSession(w http.ResponseWriter, r *http.Request, data SessionData) error {
	payload, err := json.Marshal(data)
	if err != nil {
		return err
	}
	encoded := base64.URLEncoding.EncodeToString(payload)
	sig := a.sign(encoded)
	value := encoded + "." + sig

	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    value,
		Path:     "/",
		MaxAge:   a.sessionDays * 24 * 3600,
		HttpOnly: true,
		Secure:   isSecureRequest(r),
		SameSite: http.SameSiteLaxMode,
	})
	return nil
}

// ValidateRequest 从请求 cookie 解析并验证会话。
// 返回 ErrNotAuthenticated 表示未登录或过期。
func (a *Authenticator) ValidateRequest(r *http.Request) (*SessionData, error) {
	cookie, err := r.Cookie(sessionCookieName)
	if err != nil {
		return nil, ErrNotAuthenticated
	}

	data, err := a.parseSession(cookie.Value)
	if err != nil {
		return nil, err
	}
	if !data.Authenticated {
		return nil, ErrNotAuthenticated
	}
	// 检查过期
	expire := data.LoginTime.AddDate(0, 0, a.sessionDays)
	if time.Now().After(expire) {
		return nil, ErrNotAuthenticated
	}
	// 校验 session 版本号：改密码后 version 递增，旧 session 失效
	currentVerStr, _ := a.store.GetSetting(r.Context(), "session_version", "0")
	currentVer, _ := strconv.Atoi(currentVerStr)
	if data.Version != currentVer {
		return nil, ErrNotAuthenticated
	}
	return data, nil
}

// parseSession 解码并验签会话 cookie 值。
func (a *Authenticator) parseSession(value string) (*SessionData, error) {
	parts := strings.SplitN(value, ".", 2)
	if len(parts) != 2 {
		return nil, ErrInvalidCookie
	}
	encoded, sig := parts[0], parts[1]
	if !hmac.Equal([]byte(sig), []byte(a.sign(encoded))) {
		return nil, ErrInvalidCookie
	}
	payload, err := base64.URLEncoding.DecodeString(encoded)
	if err != nil {
		return nil, ErrInvalidCookie
	}
	var data SessionData
	if err := json.Unmarshal(payload, &data); err != nil {
		return nil, ErrInvalidCookie
	}
	return &data, nil
}

// sign 计算值的 HMAC-SHA256 签名（hex 编码）。
func (a *Authenticator) sign(value string) string {
	mac := hmac.New(sha256.New, a.secretKey)
	mac.Write([]byte(value))
	return base64.URLEncoding.EncodeToString(mac.Sum(nil))
}

// ChangePassword 校验旧密码后更新密码。
func (a *Authenticator) ChangePassword(ctx context.Context, oldPwd, newPwd string) error {
	if len(newPwd) < 8 {
		return errors.New("新密码至少 8 位")
	}
	hash, err := a.store.GetSetting(ctx, "auth_password", "")
	if err != nil {
		return err
	}
	if hash == "" || !CheckPassword(oldPwd, hash) {
		return errors.New("当前密码错误")
	}
	newHash, err := HashPassword(newPwd)
	if err != nil {
		return fmt.Errorf("哈希密码失败: %w", err)
	}
	if err := a.store.SetSetting(ctx, "auth_password", newHash); err != nil {
		return err
	}
	// 递增 session_version 使所有旧 session 失效（防 cookie 被盗后改密码无效）
	verStr, _ := a.store.GetSetting(ctx, "session_version", "0")
	ver, _ := strconv.Atoi(verStr)
	return a.store.SetSetting(ctx, "session_version", strconv.Itoa(ver+1))
}

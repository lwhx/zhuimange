import pytest
import re
import os
from app.main import create_app


class TestThemeConfig:
    
    def test_theme_preview_page_loads(self, auth_client):
        response = auth_client.get('/theme-preview')
        assert response.status_code == 200
    
    def test_theme_preview_page_contains_theme_selector(self, auth_client):
        response = auth_client.get('/theme-preview')
        html = response.data.decode('utf-8')
        assert 'data-theme' in html or 'theme' in html.lower()
    
    def test_base_page_contains_preload_script(self, auth_client):
        response = auth_client.get('/')
        html = response.data.decode('utf-8')
        assert 'localStorage' in html
        assert 'data-theme' in html
        assert '--bg-primary' in html
    
    def test_themes_css_file_exists(self, app):
        static_folder = app.static_folder
        themes_css_path = os.path.join(static_folder, 'themes.css')
        assert os.path.exists(themes_css_path)
    
    def test_app_js_file_exists(self, app):
        static_folder = app.static_folder
        app_js_path = os.path.join(static_folder, 'app.js')
        assert os.path.exists(app_js_path)
    
    def test_theme_css_file_exists(self, app):
        static_folder = app.static_folder
        theme_css_path = os.path.join(static_folder, 'theme.css')
        assert os.path.exists(theme_css_path)


class TestThemeCSSVariables:
    
    def test_themes_css_contains_all_theme_variants(self, app):
        static_folder = app.static_folder
        themes_css_path = os.path.join(static_folder, 'themes.css')
        
        with open(themes_css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        expected_themes = [
            'data-theme="neon-purple"',
            'data-theme="neon-purple-light"',
            'data-theme="ocean-blue"',
            'data-theme="ocean-blue-light"',
            'data-theme="sunset-orange"',
            'data-theme="sunset-orange-light"',
            'data-theme="emerald-green"',
            'data-theme="emerald-green-light"',
            'data-theme="sakura-pink"',
            'data-theme="sakura-pink-light"'
        ]
        
        for theme_variant in expected_themes:
            assert theme_variant in content, f"Missing theme variant: {theme_variant}"
    
    def test_themes_css_contains_required_variables(self, app):
        static_folder = app.static_folder
        themes_css_path = os.path.join(static_folder, 'themes.css')
        
        with open(themes_css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_variables = [
            '--bg-primary',
            '--bg-secondary',
            '--bg-tertiary',
            '--text-primary',
            '--text-secondary',
            '--accent'
        ]
        
        for variable in required_variables:
            assert variable in content, f"Missing CSS variable: {variable}"
    
    def test_themes_css_background_colors_differ_by_theme(self, app):
        static_folder = app.static_folder
        themes_css_path = os.path.join(static_folder, 'themes.css')
        
        with open(themes_css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        bg_primary_pattern = r'--bg-primary:\s*(#[a-fA-F0-9]{6}|#[a-fA-F0-9]{3})'
        bg_colors = re.findall(bg_primary_pattern, content)
        
        assert len(bg_colors) >= 10, "Should have at least 10 background colors (5 themes × 2 modes)"
        
        unique_colors = set(bg_colors)
        assert len(unique_colors) >= 5, "Should have at least 5 different background colors for different themes"
    
    def test_base_html_uses_css_variables(self, app):
        template_folder = app.template_folder
        base_html_path = os.path.join(template_folder, 'base.html')
        
        with open(base_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'var(--bg-primary)' in content or '--bg-primary' in content
        assert 'var(--text-primary)' in content or '--text-primary' in content
        
        # 检查 body 标签不包含硬编码背景色
        body_pattern = r'<body[^>]*style=[^>]*background\s*:\s*#[0-9a-fA-F]{3,6}'
        assert not re.search(body_pattern, content), "Body tag should not have hardcoded background style"


class TestThemeJavaScript:
    
    def test_app_js_contains_theme_manager(self, app):
        static_folder = app.static_folder
        app_js_path = os.path.join(static_folder, 'app.js')
        
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'ThemeManager' in content
        assert 'setTheme' in content
        assert 'setMode' in content
        assert 'localStorage' in content
    
    def test_app_js_contains_all_themes(self, app):
        static_folder = app.static_folder
        app_js_path = os.path.join(static_folder, 'app.js')
        
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        expected_themes = ['neon-purple', 'ocean-blue', 'sunset-orange', 'emerald-green', 'sakura-pink']
        
        for theme in expected_themes:
            assert theme in content, f"Missing theme in JavaScript: {theme}"
    
    def test_app_js_contains_theme_update_function(self, app):
        static_folder = app.static_folder
        app_js_path = os.path.join(static_folder, 'app.js')
        
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'updateThemeDropdownActive' in content
        assert 'DOMContentLoaded' in content
    
    def test_app_js_data_theme_attribute_update(self, app):
        static_folder = app.static_folder
        app_js_path = os.path.join(static_folder, 'app.js')
        
        with open(app_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'setAttribute' in content
        assert 'data-theme' in content


class TestThemePreloadScript:
    
    def test_base_html_preload_script_structure(self, app):
        template_folder = app.template_folder
        base_html_path = os.path.join(template_folder, 'base.html')
        
        with open(base_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert '(function()' in content
        assert 'localStorage.getItem' in content
        assert 'document.documentElement.setAttribute' in content
        assert 'setAttribute' in content
    
    def test_base_html_preload_script_theme_fallback(self, app):
        template_folder = app.template_folder
        base_html_path = os.path.join(template_folder, 'base.html')
        
        with open(base_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert "|| 'neon-purple'" in content
        assert "|| 'dark'" in content
    
    def test_base_html_preload_script_all_themes(self, app):
        template_folder = app.template_folder
        base_html_path = os.path.join(template_folder, 'base.html')
        
        with open(base_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        expected_themes = ['neon-purple', 'ocean-blue', 'sunset-orange', 'emerald-green', 'sakura-pink']
        
        for theme in expected_themes:
            assert f"'{theme}'" in content, f"Missing theme in preload script: {theme}"
    
    def test_base_html_preload_script_system_preference(self, app):
        template_folder = app.template_folder
        base_html_path = os.path.join(template_folder, 'base.html')
        
        with open(base_html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'prefers-color-scheme' in content
        assert 'matchMedia' in content


class TestThemeWCAGCompliance:
    
    def test_theme_backgrounds_not_black(self, app):
        static_folder = app.static_folder
        themes_css_path = os.path.join(static_folder, 'themes.css')
        
        with open(themes_css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        bg_pattern = r'--bg-primary:\s*(#[a-fA-F0-9]{6})'
        bg_colors = re.findall(bg_pattern, content)
        
        black_like_colors = ['#000000', '#000001', '#010000', '#0a0a0a', '#050505']
        
        for color in bg_colors:
            assert color.lower() not in black_like_colors, f"Theme background color is too dark: {color}"
    
    def test_theme_text_not_white(self, app):
        static_folder = app.static_folder
        themes_css_path = os.path.join(static_folder, 'themes.css')
        
        with open(themes_css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        text_pattern = r'--text-primary:\s*(#[a-fA-F0-9]{6})'
        text_colors = re.findall(text_pattern, content)
        
        white_like_colors = ['#ffffff', '#fffffe', '#feffff', '#fafafa', '#f5f5f5']
        
        for color in text_colors:
            assert color.lower() not in white_like_colors, f"Theme text color is too bright: {color}"
    
    def test_theme_preview_page_has_main_element(self, auth_client):
        response = auth_client.get('/theme-preview')
        html = response.data.decode('utf-8')
        assert '<main' in html

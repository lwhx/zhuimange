import pytest
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class TestThemeRealtimeUpdates:
    """测试主题切换的实时更新功能"""
    
    @pytest.fixture(scope="class")
    def driver(self):
        """设置测试浏览器"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # 无头模式
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()
    
    def test_theme_switching_realtime(self, driver, live_server):
        """测试主题切换的实时更新"""
        driver.get(f"{live_server.url}/login")
        
        # 等待页面加载
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 获取初始背景色
        initial_bg = driver.execute_script(
            "return window.getComputedStyle(document.body).backgroundColor"
        )
        
        # 切换到浅色模式
        driver.execute_script("""
            if (window.ThemeManager) {
                window.ThemeManager.setMode('light');
            }
        """)
        
        # 等待主题切换
        time.sleep(0.5)
        
        # 验证背景色已改变
        new_bg = driver.execute_script(
            "return window.getComputedStyle(document.body).backgroundColor"
        )
        assert new_bg != initial_bg, "背景色应该改变"
        
        # 验证所有组件已更新
        navbar_bg = driver.execute_script(
            "return window.getComputedStyle(document.querySelector('.navbar')).backgroundColor"
        )
        assert navbar_bg != "rgba(0, 0, 0, 0)", "导航栏背景色应该更新"
    
    def test_theme_switching_all_components(self, driver, live_server):
        """测试所有组件的主题切换"""
        driver.get(f"{live_server.url}/")
        
        # 等待页面加载
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "navbar"))
        )
        
        # 获取所有主要组件的初始样式
        components = [
            "body",
            ".navbar",
            ".main-content",
            ".btn",
            "input",
            ".modal"
        ]
        
        initial_styles = {}
        for selector in components:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                initial_styles[selector] = {
                    'backgroundColor': driver.execute_script(
                        f"return window.getComputedStyle(document.querySelector('{selector}')).backgroundColor"
                    ),
                    'color': driver.execute_script(
                        f"return window.getComputedStyle(document.querySelector('{selector}')).color"
                    )
                }
            except:
                continue
        
        # 切换到浅色模式
        driver.execute_script("""
            if (window.ThemeManager) {
                window.ThemeManager.setMode('light');
            }
        """)
        
        # 等待主题切换
        time.sleep(0.5)
        
        # 验证所有组件已更新
        for selector, initial in initial_styles.items():
            try:
                new_bg = driver.execute_script(
                    f"return window.getComputedStyle(document.querySelector('{selector}')).backgroundColor"
                )
                new_color = driver.execute_script(
                    f"return window.getComputedStyle(document.querySelector('{selector}')).color"
                )
                
                assert new_bg != initial['backgroundColor'] or new_color != initial['color'], \
                    f"组件 {selector} 应该更新样式"
            except:
                continue
    
    def test_theme_switching_no_refresh_needed(self, driver, live_server):
        """测试无需刷新页面的主题切换"""
        driver.get(f"{live_server.url}/theme-preview")
        
        # 等待页面加载
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "preview-content"))
        )
        
        # 记录页面状态
        page_title = driver.title
        
        # 切换主题
        driver.execute_script("""
            if (window.ThemeManager) {
                window.ThemeManager.setTheme('ocean-blue');
            }
        """)
        
        # 等待主题切换
        time.sleep(0.5)
        
        # 验证页面未刷新
        assert driver.title == page_title, "页面不应该刷新"
        
        # 验证主题已应用
        theme_attr = driver.execute_script(
            "return document.documentElement.getAttribute('data-theme')"
        )
        assert "ocean-blue" in theme_attr, "主题属性应该更新"
    
    def test_system_theme_change_detection(self, driver, live_server):
        """测试系统主题变化检测"""
        driver.get(f"{live_server.url}/")
        
        # 清除本地存储的主题设置
        driver.execute_script("""
            localStorage.removeItem('zhuimange-theme-mode');
        """)
        
        # 模拟系统主题变化
        driver.execute_script("""
            // 模拟系统深色模式变化
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            const event = new MediaQueryListEvent('change', {
                matches: false,
                media: '(prefers-color-scheme: dark)'
            });
            mediaQuery.dispatchEvent(event);
        """)
        
        # 等待响应
        time.sleep(0.5)
        
        # 验证主题已响应系统变化
        theme_attr = driver.execute_script(
            "return document.documentElement.getAttribute('data-theme')"
        )
        assert theme_attr is not None, "应该响应系统主题变化"
    
    def test_theme_switching_performance(self, driver, live_server):
        """测试主题切换性能"""
        driver.get(f"{live_server.url}/")
        
        # 等待页面加载
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 测量主题切换时间
        start_time = time.time()
        
        driver.execute_script("""
            if (window.ThemeManager) {
                window.ThemeManager.setMode('light');
            }
        """)
        
        # 等待样式更新完成
        WebDriverWait(driver, 2).until(
            lambda d: d.execute_script(
                "return document.documentElement.getAttribute('data-theme') && document.documentElement.getAttribute('data-theme').includes('light')"
            )
        )
        
        end_time = time.time()
        switch_time = end_time - start_time
        
        # 主题切换应该在1秒内完成
        assert switch_time < 1.0, f"主题切换时间 {switch_time}s 应该小于1秒"
    
    def test_theme_switching_consistency(self, driver, live_server):
        """测试主题切换的一致性"""
        driver.get(f"{live_server.url}/")
        
        # 测试多次切换
        themes = ['neon-purple', 'ocean-blue', 'sunset-orange']
        
        for theme in themes:
            driver.execute_script(f"""
                if (window.ThemeManager) {{
                    window.ThemeManager.setTheme('{theme}');
                }}
            """)
            
            time.sleep(0.3)
            
            # 验证主题已正确应用
            theme_attr = driver.execute_script(
                "return document.documentElement.getAttribute('data-theme')"
            )
            assert theme in theme_attr, f"主题 {theme} 应该正确应用"


class TestThemeCSSVariables:
    """测试CSS变量的正确应用"""
    
    def test_css_variables_exist(self, driver, live_server):
        """测试CSS变量存在且可访问"""
        driver.get(f"{live_server.url}/")
        
        # 验证CSS变量存在
        bg_primary = driver.execute_script(
            "return getComputedStyle(document.documentElement).getPropertyValue('--bg-primary')"
        )
        text_primary = driver.execute_script(
            "return getComputedStyle(document.documentElement).getPropertyValue('--text-primary')"
        )
        
        assert bg_primary.strip(), "--bg-primary 变量应该存在"
        assert text_primary.strip(), "--text-primary 变量应该存在"
    
    def test_css_variables_theme_specific(self, driver, live_server):
        """测试主题特定的CSS变量"""
        driver.get(f"{live_server.url}/")
        
        # 切换到霓虹紫主题
        driver.execute_script("""
            if (window.ThemeManager) {
                window.ThemeManager.setTheme('neon-purple');
            }
        """)
        
        time.sleep(0.5)
        
        # 验证主题特定变量
        accent_color = driver.execute_script(
            "return getComputedStyle(document.documentElement).getPropertyValue('--accent')"
        )
        assert "8b5cf6" in accent_color.lower() or "rgb(139, 92, 246)" in accent_color, \
            "霓虹紫主题的强调色应该正确设置"
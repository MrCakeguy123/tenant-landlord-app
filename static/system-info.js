/**
 * System Information Detection
 * Detects browser, OS, and device information
 */

(function() {
  'use strict';

  /**
   * Detect browser information
   */
  function detectBrowser() {
    const userAgent = navigator.userAgent;
    const browsers = {
      'Chrome': /Chrome\/(\d+)/,
      'Safari': /Safari\/(\d+)/,
      'Firefox': /Firefox\/(\d+)/,
      'Edge': /Edg\/(\d+)/,
      'Opera': /OPR\/(\d+)/,
      'IE': /MSIE (\d+)|Trident.*rv:(\d+)/
    };

    // Check Edge first (before Chrome, as Edge contains Chrome in UA)
    if (browsers.Edge.test(userAgent)) {
      const version = userAgent.match(browsers.Edge)[1];
      return { name: 'Edge', version: version, icon: '🌐' };
    }

    // Check Opera (before Chrome, as Opera contains Chrome in UA)
    if (browsers.Opera.test(userAgent)) {
      const version = userAgent.match(browsers.Opera)[1];
      return { name: 'Opera', version: version, icon: '🎭' };
    }

    // Check Chrome (before Safari, as Chrome contains Safari in UA)
    if (browsers.Chrome.test(userAgent) && !browsers.Edge.test(userAgent)) {
      const version = userAgent.match(browsers.Chrome)[1];
      return { name: 'Chrome', version: version, icon: '🔵' };
    }

    // Check Safari
    if (browsers.Safari.test(userAgent) && !browsers.Chrome.test(userAgent)) {
      const version = userAgent.match(browsers.Safari)[1];
      return { name: 'Safari', version: version, icon: '🧭' };
    }

    // Check Firefox
    if (browsers.Firefox.test(userAgent)) {
      const version = userAgent.match(browsers.Firefox)[1];
      return { name: 'Firefox', version: version, icon: '🦊' };
    }

    // Check IE
    if (browsers.IE.test(userAgent)) {
      const match = userAgent.match(browsers.IE);
      const version = match[1] || match[2];
      return { name: 'IE', version: version, icon: '⚠️' };
    }

    return { name: 'Unknown', version: '', icon: '❓' };
  }

  /**
   * Detect operating system
   */
  function detectOS() {
    const userAgent = navigator.userAgent;
    const platform = navigator.platform;

    // iOS detection
    if (/iPad|iPhone|iPod/.test(userAgent) && !window.MSStream) {
      const version = userAgent.match(/OS (\d+)_(\d+)/);
      return {
        name: 'iOS',
        version: version ? `${version[1]}.${version[2]}` : '',
        icon: '📱'
      };
    }

    // Android detection
    if (/Android/.test(userAgent)) {
      const version = userAgent.match(/Android (\d+(\.\d+)?)/);
      return {
        name: 'Android',
        version: version ? version[1] : '',
        icon: '🤖'
      };
    }

    // macOS detection
    if (/Mac/.test(platform)) {
      return { name: 'macOS', version: '', icon: '🍎' };
    }

    // Windows detection
    if (/Win/.test(platform)) {
      let version = '';
      if (/Windows NT 10/.test(userAgent)) version = '10/11';
      else if (/Windows NT 6.3/.test(userAgent)) version = '8.1';
      else if (/Windows NT 6.2/.test(userAgent)) version = '8';
      else if (/Windows NT 6.1/.test(userAgent)) version = '7';
      return { name: 'Windows', version: version, icon: '🪟' };
    }

    // Linux detection
    if (/Linux/.test(platform)) {
      return { name: 'Linux', version: '', icon: '🐧' };
    }

    return { name: 'Unknown', version: '', icon: '❓' };
  }

  /**
   * Detect device type
   */
  function detectDeviceType() {
    const userAgent = navigator.userAgent;

    if (/tablet|ipad|playbook|silk/i.test(userAgent)) {
      return 'Tablet';
    }

    if (/Mobile|Android|iP(hone|od)|IEMobile|BlackBerry|Kindle|Silk-Accelerated|(hpw|web)OS|Opera M(obi|ini)/.test(userAgent)) {
      return 'Mobile';
    }

    return 'Desktop';
  }

  /**
   * Get screen resolution
   */
  function getScreenInfo() {
    return {
      width: window.screen.width,
      height: window.screen.height,
      pixelRatio: window.devicePixelRatio || 1
    };
  }

  /**
   * Update footer with system information
   */
  function updateFooter() {
    const browser = detectBrowser();
    const os = detectOS();
    const deviceType = detectDeviceType();
    const screen = getScreenInfo();

    // Update browser info
    const browserElement = document.getElementById('footer-browser');
    if (browserElement) {
      const browserText = browser.version
        ? `${browser.icon} ${browser.name} ${browser.version}`
        : `${browser.icon} ${browser.name}`;
      browserElement.textContent = browserText;
    }

    // Update OS info
    const osElement = document.getElementById('footer-os');
    if (osElement) {
      const osText = os.version
        ? `${os.icon} ${os.name} ${os.version}`
        : `${os.icon} ${os.name}`;
      osElement.textContent = osText;
    }

    // Update device info
    const deviceElement = document.getElementById('footer-device');
    if (deviceElement) {
      deviceElement.textContent = `📱 ${deviceType}`;
    }

    // Update screen info
    const screenElement = document.getElementById('footer-screen');
    if (screenElement) {
      screenElement.textContent = `🖥️ ${screen.width}×${screen.height}`;
    }

    // Log analytics if endpoint exists
    logAnalytics({
      browser: `${browser.name} ${browser.version}`,
      os: `${os.name} ${os.version}`,
      device_type: deviceType,
      screen_width: screen.width,
      screen_height: screen.height,
      pixel_ratio: screen.pixelRatio,
      user_agent: navigator.userAgent,
      language: navigator.language,
      timestamp: new Date().toISOString()
    });
  }

  /**
   * Send analytics to server
   */
  function logAnalytics(data) {
    // Only log if user is logged in (check if we're not on login page)
    const isLoggedIn = !window.location.pathname.includes('/login') &&
                       !window.location.pathname.includes('/setup');

    if (!isLoggedIn) {
      console.debug('Analytics: Skipping (not logged in)');
      return;
    }

    console.debug('Analytics: Sending data:', data);

    fetch('/api/log-analytics', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data)
    })
    .then(function(response) {
      if (response.ok) {
        return response.json();
      }
      throw new Error('Analytics response not OK: ' + response.status);
    })
    .then(function(result) {
      console.debug('Analytics logged successfully:', result);
    })
    .catch(function(error) {
      // Log errors for debugging but don't break the app
      console.error('Analytics logging failed:', error);
    });
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', updateFooter);
  } else {
    updateFooter();
  }
})();

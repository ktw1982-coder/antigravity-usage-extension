document.addEventListener('DOMContentLoaded', () => {
  const statusBadge = document.getElementById('status-badge');
  const mainContent = document.getElementById('main-content');
  const errorContent = document.getElementById('error-content');
  const lastUpdated = document.getElementById('last-updated');
  
  // Weekly elements
  const weeklyPct = document.getElementById('weekly-pct');
  const weeklyBar = document.getElementById('weekly-bar');
  const weeklyRem = document.getElementById('weekly-rem');
  const weeklyRef = document.getElementById('weekly-ref');
  
  // 5-Hour elements
  const fiveHourPct = document.getElementById('five-hour-pct');
  const fiveHourBar = document.getElementById('five-hour-bar');
  const fiveHourRem = document.getElementById('five-hour-rem');
  const fiveHourRef = document.getElementById('five-hour-ref');
  
  // Buttons
  const refreshBtn = document.getElementById('refresh-btn');
  const retryBtn = document.getElementById('retry-btn');
  
  const API_URL = 'http://localhost:8484/usage';

  async function fetchUsage() {
    refreshBtn.classList.add('spinning');
    statusBadge.textContent = 'Refreshing';
    statusBadge.className = 'badge ok';
    
    try {
      const response = await fetch(API_URL);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.status === 'Error') {
        const errType = data.error_type || 'UNKNOWN';
        const msg = data.error_message || 'Backend scraping error';
        throw new Error(`[${errType}] ${msg}`);
      }
      
      // Update badge
      statusBadge.textContent = 'Live';
      statusBadge.className = 'badge ok';
      
      // Toggle visibility
      mainContent.classList.remove('hidden');
      errorContent.classList.add('hidden');
      
      // Support both new & legacy structure (Gemini primary)
      const gWeeklyPct = data.gemini_weekly_percentage !== undefined ? data.gemini_weekly_percentage : (data.weekly_percentage || 0.0);
      const gWeeklyRem = data.gemini_weekly_remaining || data.weekly_remaining || '0% remaining';
      const gWeeklyRef = data.gemini_weekly_refresh || data.weekly_refresh || 'Unknown';
      
      weeklyPct.textContent = `${gWeeklyPct.toFixed(1)}%`;
      weeklyBar.style.width = `${gWeeklyPct}%`;
      weeklyRem.textContent = gWeeklyRem;
      weeklyRef.textContent = `Refreshes in ${gWeeklyRef}`;
      setBarColor(weeklyBar, gWeeklyPct);
      
      // 5-Hour Quota binding
      const gFiveHourPct = data.gemini_five_hour_percentage !== undefined ? data.gemini_five_hour_percentage : (data.five_hour_percentage || 0.0);
      const gFiveHourRem = data.gemini_five_hour_remaining || data.five_hour_remaining || '0% remaining';
      const gFiveHourRef = data.gemini_five_hour_refresh || data.five_hour_refresh || 'Unknown';
      
      fiveHourPct.textContent = `${gFiveHourPct.toFixed(1)}%`;
      fiveHourBar.style.width = `${gFiveHourPct}%`;
      fiveHourRem.textContent = gFiveHourRem;
      fiveHourRef.textContent = `Refreshes in ${gFiveHourRef}`;
      setBarColor(fiveHourBar, gFiveHourPct);
      
      // Last update formatting
      if (data.last_updated) {
        const date = new Date(data.last_updated * 1000);
        const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        lastUpdated.textContent = `Last update: ${timeStr}`;
      } else {
        lastUpdated.textContent = 'Last update: Just now';
      }
      
    } catch (error) {
      console.error('Failed to fetch usage data:', error);
      statusBadge.textContent = 'Offline';
      statusBadge.className = 'badge error';
      mainContent.classList.add('hidden');
      errorContent.classList.remove('hidden');
      
      const errorMsgEl = errorContent.querySelector('p');
      if (errorMsgEl) {
        errorMsgEl.textContent = error.message || 'Make sure the backend or macOS app is running on port 8484.';
      }
      lastUpdated.textContent = 'Connection failed';
    } finally {
      setTimeout(() => {
        refreshBtn.classList.remove('spinning');
      }, 500);
    }
  }

  function setBarColor(barElement, percentage) {
    barElement.classList.remove('warning', 'danger');
    if (percentage >= 90.0) {
      barElement.classList.add('danger');
    } else if (percentage >= 80.0) {
      barElement.classList.add('warning');
    }
  }

  // Event Listeners
  refreshBtn.addEventListener('click', fetchUsage);
  retryBtn.addEventListener('click', fetchUsage);

  // Initial Fetch
  fetchUsage();
});

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
    // Show spinning animation
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
        throw new Error(data.error_message || 'Backend scraping error');
      }
      
      // Update badge
      statusBadge.textContent = 'Live';
      statusBadge.className = 'badge ok';
      
      // Toggle visibility
      mainContent.classList.remove('hidden');
      errorContent.classList.add('hidden');
      
      // Weekly Quota binding
      const weeklyPctVal = data.weekly_percentage || 0.0;
      weeklyPct.textContent = `${weeklyPctVal.toFixed(1)}%`;
      weeklyBar.style.width = `${weeklyPctVal}%`;
      weeklyRem.textContent = data.weekly_remaining || '0% remaining';
      weeklyRef.textContent = `Refreshes in ${data.weekly_refresh || 'Unknown'}`;
      
      // Update progress bar color based on percentage remaining
      setBarColor(weeklyBar, weeklyPctVal);
      
      // 5-Hour Quota binding
      const fiveHourPctVal = data.five_hour_percentage || 0.0;
      fiveHourPct.textContent = `${fiveHourPctVal.toFixed(1)}%`;
      fiveHourBar.style.width = `${fiveHourPctVal}%`;
      fiveHourRem.textContent = data.five_hour_remaining || '0% remaining';
      fiveHourRef.textContent = `Refreshes in ${data.five_hour_refresh || 'Unknown'}`;
      
      setBarColor(fiveHourBar, fiveHourPctVal);
      
      // Last update formatting
      if (data.last_updated) {
        const date = new Date(data.last_updated * 1000);
        const timeStr = date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
      lastUpdated.textContent = 'Connection failed';
    } finally {
      // Remove spin animation after a slight delay for better UX
      setTimeout(() => {
        refreshBtn.classList.remove('spinning');
      }, 500);
    }
  }

  function setBarColor(barElement, percentage) {
    // Reset colors
    barElement.classList.remove('warning', 'danger');
    
    // Set color based on remaining %
    if (percentage <= 20.0) {
      barElement.classList.add('danger');
    } else if (percentage <= 50.0) {
      barElement.classList.add('warning');
    }
  }

  // Event Listeners
  refreshBtn.addEventListener('click', fetchUsage);
  retryBtn.addEventListener('click', fetchUsage);

  // Initial Fetch
  fetchUsage();
});

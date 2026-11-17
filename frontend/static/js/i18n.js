/**
 * CivicLens Internationalization (i18n) Engine
 * ============================================
 * Centralized, accessible translation system supporting English (en) and ಕನ್ನಡ (kn).
 * Automatically updates DOM elements with data-i18n attributes, handles persistent
 * user language preferences in localStorage, and dispatches change events.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.CivicLensI18n = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const STORAGE_KEY = 'civiclens_lang';
  const DEFAULT_LANG = 'en';

  const DICTIONARY = {
    en: {
      // Navigation
      "nav.home": "Home Portal",
      "nav.citizen_dashboard": "Citizen Dashboard",
      "nav.report": "Report an Issue",
      "nav.my_reports": "My Reports",
      "nav.map": "Public Map",
      "nav.dashboard": "Live Monitor",
      "nav.municipal": "Municipal Triage",
      "nav.media_management": "Impact Showcase",
      "nav.verification": "Verification Queue",
      "nav.departments": "Departments & Officers",
      "nav.transparency": "Civic Transparency",
      "nav.notifications": "Notifications",
      "nav.match_review": "Duplicate Review",
      "nav.login": "Citizen Login",
      "nav.logout": "Log Out",
      "nav.language": "Language",

      // Citizen Report Form
      "report.heading": "Report Infrastructure Defect",
      "report.subheading": "Provide photos, mark defect location, and describe hazards in English or Kannada. Multiple reports at the same defect site automatically link to a canonical municipal incident.",
      "report.photos": "1. Photographic / Video Evidence (Up to 5 files)",
      "report.photos_hint": "Accepted: JPEG, PNG, WebP, MP4 (Max 16 MB each). Clear road photos help engineering triage crews.",
      "report.title": "2. Brief Defect Title",
      "report.title_placeholder": "e.g. Deep pothole on outer ring road near bus stop",
      "report.location": "3. Defect Location (Interactive Pin & GPS)",
      "report.gps_btn": "📍 Capture Device GPS",
      "report.recenter_btn": "🎯 Recenter Map Pin",
      "report.map_hint": "Tap anywhere on the map or drag the pin to mark the exact location of the defect.",
      "report.landmark": "Street / Landmark Address (Optional)",
      "report.landmark_placeholder": "e.g. 100 Feet Rd, Indiranagar, near Metro Pillar 124",
      "report.category": "4. Defect Category",
      "report.severity": "5. Estimated Severity",
      "report.sev_minor": "Minor",
      "report.sev_moderate": "Moderate",
      "report.sev_severe": "Severe",
      "report.sev_critical": "Critical",
      "report.disclaimer": "⚠️ Citizen Severity Disclaimer: Your severity selection represents an initial citizen observation. Final priority triage and classification are determined by Municipal Engineering evaluation.",
      "report.desc": "6. Description & Safety Hazards",
      "report.desc_placeholder": "Describe the size, depth, danger to two-wheelers, pedestrians, or water accumulation... (English or ಕನ್ನಡ)",
      "report.submit_btn": "🚀 Submit Defect Report",
      "report.submitting": "⏳ Submitting Report...",
      "report.success_title": "Report Submitted Successfully",
      "report.success_ref": "Your grievance reference code is",
      "report.success_triage": "Municipal engineering dispatch and automated triage are processing your report.",
      "report.btn_view_details": "View Report Details →",
      "report.btn_submit_another": "Submit Another Defect",

      // Categories
      "cat.pothole": "Pothole / Road Depression",
      "cat.road_damage": "Asphalt Cave-in / Surface Damage",
      "cat.drainage": "Open Manhole / Clogged Storm Drain",
      "cat.broken_streetlight": "Broken Streetlight / Electrical Hazard",
      "cat.water_leakage": "BWSSB Water Pipeline Leak",
      "cat.garbage": "Garbage / Construction Debris on Road",
      "cat.bridge_damage": "Bridge or Flyover Structural Defect",
      "cat.other": "Other Civic Infrastructure Defect",

      // Statuses
      "status.submitted": "Submitted",
      "status.under_review": "Under Review",
      "status.linked": "Linked to Incident",
      "status.resolved": "Resolved",
      "status.rejected": "Rejected",
      "status.acknowledged": "Acknowledged",

      // Language & Translation Badges
      "lang.detecting": "Detecting language...",
      "lang.detected_kn": "Detected: Kannada (ಕನ್ನಡ)",
      "lang.detected_en": "Detected: English",
      "lang.detected_mixed": "Detected: Mixed (Kannada–English)",
      "lang.original_label": "Original Submission",
      "lang.translated_label": "Verified English Translation",
      "lang.summary_label": "AI Brief Summary",
      "lang.address_structured": "Normalized Location Context",

      // Common actions
      "common.close": "Close",
      "common.back": "Back",
      "common.search": "Search reports...",
      "common.filter": "Filter",
    },

    kn: {
      // Navigation
      "nav.home": "ಮುಖಪುಟ",
      "nav.citizen_dashboard": "ನಾಗರಿಕರ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
      "nav.report": "ಸಮಸ್ಯೆ ವರದಿ ಮಾಡಿ",
      "nav.my_reports": "ನನ್ನ ವರದಿಗಳು",
      "nav.map": "ಸಾರ್ವಜನಿಕ ನಕ್ಷೆ",
      "nav.dashboard": "ಲೈವ್ ಮಾನಿಟರ್",
      "nav.municipal": "ಪಾಲಿಕೆ ತಪಾಸಣೆ",
      "nav.media_management": "ಪ್ರಭಾವ ಪ್ರದರ್ಶನ",
      "nav.verification": "ಪರಿಶೀಲನಾ ಸರದಿ",
      "nav.departments": "ಇಲಾಖೆಗಳು ಮತ್ತು ಅಧಿಕಾರಿಗಳು",
      "nav.transparency": "ನಾಗರಿಕ ಪಾರದರ್ಶಕತೆ",
      "nav.notifications": "ಅಧಿಸೂಚನೆಗಳು",
      "nav.match_review": "ನಕಲಿ ವರದಿಗಳ ಪರಿಶೀಲನೆ",
      "nav.login": "ನಾಗರಿಕ ಲಾಗಿನ್",
      "nav.logout": "ನಿರ್ಗಮಿಸಿ",
      "nav.language": "ಭಾಷೆ",

      // Citizen Report Form
      "report.heading": "ರಸ್ತೆ ಅಥವಾ ಮೂಲಸೌಕರ್ಯ ದೋಷ ವರದಿ ಮಾಡಿ",
      "report.subheading": "ಫೋಟೋಗಳನ್ನು ಒದಗಿಸಿ, ನಕ್ಷೆಯಲ್ಲಿ ಸ್ಥಳವನ್ನು ಗುರುತಿಸಿ ಮತ್ತು ಕನ್ನಡ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ವಿವರಣೆ ನೀಡಿ. ಒಂದೇ ಸ್ಥಳದಲ್ಲಿರುವ ಬಹು ವರದಿಗಳು ಸ್ವಯಂಚಾಲಿತವಾಗಿ ವಿಲೀನಗೊಳ್ಳುತ್ತವೆ.",
      "report.photos": "1. ಛಾಯಾಚಿತ್ರ ಅಥವಾ ವೀಡಿಯೊ ಸಾಕ್ಷ್ಯ (ಗರಿಷ್ಠ 5 ಕಡತಗಳು)",
      "report.photos_hint": "ಸ್ವೀಕರಿಸಲಾಗುವುದು: JPEG, PNG, WebP, MP4 (ಪ್ರತಿಯೊಂದೂ ಗರಿಷ್ಠ 16 MB). ಸ್ಪಷ್ಟ ಫೋಟೋಗಳು ತ್ವರಿತ ದುರಸ್ತಿಗೆ ಸಹಕಾರಿ.",
      "report.title": "2. ಸಂಕ್ಷಿಪ್ತ ಶೀರ್ಷಿಕೆ",
      "report.title_placeholder": "ಉದಾ: ಬಸ್ ನಿಲ್ದಾಣದ ಬಳಿ ಹೊರವರ್ತುಲ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ",
      "report.location": "3. ದೋಷದ ಸ್ಥಳ (ನಕ್ಷೆಯಲ್ಲಿ ಪಿನ್ ಅಥವಾ GPS)",
      "report.gps_btn": "📍 ಮೊಬೈಲ್ GPS ಪಡೆಯಿರಿ",
      "report.recenter_btn": "🎯 ನಕ್ಷೆಯ ಪಿನ್ ಮರುಹೊಂದಿಸಿ",
      "report.map_hint": "ದೋಷದ ನಿಖರ ಸ್ಥಳವನ್ನು ಗುರುತಿಸಲು ನಕ್ಷೆಯ ಮೇಲೆ ಟ್ಯಾಪ್ ಮಾಡಿ ಅಥವಾ ಪಿನ್ ಎಳೆಯಿರಿ.",
      "report.landmark": "ರಸ್ತೆ / ಹತ್ತಿರದ ಪ್ರಮುಖ ಸ್ಥಳ (ಐಚ್ಛಿಕ)",
      "report.landmark_placeholder": "ಉದಾ: 100 ಅಡಿ ರಸ್ತೆ, ಇಂದಿರಾನಗರ, ಮೆಟ್ರೋ ಪಿಲ್ಲರ್ 124 ರ ಬಳಿ",
      "report.category": "4. ದೋಷದ ವರ್ಗ",
      "report.severity": "5. ಅಂದಾಜು ತೀವ್ರತೆ",
      "report.sev_minor": "ಕಡಿಮೆ",
      "report.sev_moderate": "ಮಧ್ಯಮ",
      "report.sev_severe": "ತೀವ್ರ",
      "report.sev_critical": "ಅತ್ಯಂತ ಗಂಭೀರ",
      "report.disclaimer": "⚠️ ನಾಗರಿಕರ ಗಮನಕ್ಕೆ: ನಿಮ್ಮ ತೀವ್ರತೆಯ ಅಂದಾಜು ಪ್ರಾಥಮಿಕ ಮಾಹಿತಿಯಾಗಿದೆ. ಅಂತಿಮ ನಿರ್ಧಾರವನ್ನು ಪಾಲಿಕೆ ಇಂಜಿನಿಯರಿಂಗ್ ತಂಡ ಪರಿಶೀಲಿಸುತ್ತದೆ.",
      "report.desc": "6. ವಿವರಣೆ ಮತ್ತು ಸುರಕ್ಷತಾ ಅಪಾಯಗಳು",
      "report.desc_placeholder": "ಗುಂಡಿಯ ಗಾತ್ರ, ಆಳ, ದ್ವಿಚಕ್ರ ವಾಹನಗಳಿಗೆ ಅಪಾಯ ಅಥವಾ ನೀರು ನಿಲ್ಲುವ ಬಗ್ಗೆ ವಿವರಿಸಿ... (ಕನ್ನಡ ಅಥವಾ English)",
      "report.submit_btn": "🚀 ವರದಿ ಸಲ್ಲಿಸಿ",
      "report.submitting": "⏳ ವರದಿ ಸಲ್ಲಿಸಲಾಗುತ್ತಿದೆ...",
      "report.success_title": "ವರದಿ ಯಶಸ್ವಿಯಾಗಿ ಸಲ್ಲಿಕೆಯಾಗಿದೆ",
      "report.success_ref": "ನಿಮ್ಮ ದೂರಿನ ಉಲ್ಲೇಖ ಸಂಖ್ಯೆ",
      "report.success_triage": "ಪಾಲಿಕೆಯ ಇಂಜಿನಿಯರಿಂಗ್ ತಂಡ ಹಾಗೂ ಸ್ವಯಂಚಾಲಿತ ವ್ಯವಸ್ಥೆ ನಿಮ್ಮ ವರದಿಯನ್ನು ಪರಿಶೀಲಿಸುತ್ತಿದೆ.",
      "report.btn_view_details": "ವರದಿಯ ವಿವರ ನೋಡಿ →",
      "report.btn_submit_another": "ಮತ್ತೊಂದು ದೋಷ ವರದಿ ಮಾಡಿ",

      // Categories
      "cat.pothole": "ರಸ್ತೆ ಗುಂಡಿ / ಹಳ್ಳ",
      "cat.road_damage": "ಡಾಂಬರು ಕಿತ್ತುಹೋಗಿರುವುದು / ರಸ್ತೆ ಹಾನಿ",
      "cat.drainage": "ತೆರೆದ ಮ್ಯಾನ್‌ಹೋಲ್ / ಚರಂಡಿ ಕಟ್ಟಿಕೊಂಡಿರುವುದು",
      "cat.broken_streetlight": "ಹಾಳಾದ ಬೀದಿ ದೀಪ / ವಿದ್ಯುತ್ ಅಪಾಯ",
      "cat.water_leakage": "BWSSB ನೀರಿನ ಪೈಪ್ ಸೋರಿಕೆ",
      "cat.garbage": "ರಸ್ತೆಯಲ್ಲಿ ಕಸ ಅಥವಾ ಕಟ್ಟಡ ತ್ಯಾಜ್ಯ",
      "cat.bridge_damage": "ಸೇತುವೆ ಅಥವಾ ಮೇಲ್ಸೇತುವೆ ಹಾನಿ",
      "cat.other": "ಇತರ ಮೂಲಸೌಕರ್ಯ ದೋಷ",

      // Statuses
      "status.submitted": "ಸಲ್ಲಿಸಲಾಗಿದೆ",
      "status.under_review": "ಪರಿಶೀಲನೆಯಲ್ಲಿದೆ",
      "status.linked": "ವಿಲೀನಗೊಳಿಸಲಾಗಿದೆ",
      "status.resolved": "ಪರಿಹರಿಸಲಾಗಿದೆ",
      "status.rejected": "ತಿರಸ್ಕರಿಸಲಾಗಿದೆ",
      "status.acknowledged": "ಸ್ವೀಕರಿಸಲಾಗಿದೆ",

      // Language & Translation Badges
      "lang.detecting": "ಭಾಷೆ ಗುರುತಿಸಲಾಗುತ್ತಿದೆ...",
      "lang.detected_kn": "ಗುರುತಿಸಿದ ಭಾಷೆ: ಕನ್ನಡ",
      "lang.detected_en": "ಗುರುತಿಸಿದ ಭಾಷೆ: English",
      "lang.detected_mixed": "ಗುರುತಿಸಿದ ಭಾಷೆ: ಮಿಶ್ರ ಭಾಷೆ (ಕನ್ನಡ-ಇಂಗ್ಲಿಷ್)",
      "lang.original_label": "ಮೂಲ ಸಲ್ಲಿಕೆ",
      "lang.translated_label": "ದೃಢೀಕೃತ ಇಂಗ್ಲಿಷ್ ಅನುವಾದ",
      "lang.summary_label": "AI ಸಂಕ್ಷಿಪ್ತ ವಿವರಣೆ",
      "lang.address_structured": "ದೃಢೀಕೃತ ಸ್ಥಳ ಮಾಹಿತಿ",

      // Common actions
      "common.close": "ಮುಚ್ಚಿ",
      "common.back": "ಹಿಂದಕ್ಕೆ",
      "common.search": "ವರದಿಗಳನ್ನು ಹುಡುಕಿ...",
      "common.filter": "ಫಿಲ್ಟರ್",
    }
  };

  let currentLang = DEFAULT_LANG;

  function init() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && (saved === 'kn' || saved === 'en')) {
        currentLang = saved;
      }
    } catch (e) {
      currentLang = DEFAULT_LANG;
    }
    document.documentElement.lang = currentLang;
    applyTranslations();
  }

  function t(key, fallback) {
    const dict = DICTIONARY[currentLang] || DICTIONARY[DEFAULT_LANG];
    if (dict && dict[key] !== undefined) {
      return dict[key];
    }
    const defaultDict = DICTIONARY[DEFAULT_LANG];
    if (defaultDict && defaultDict[key] !== undefined) {
      return defaultDict[key];
    }
    return fallback || key;
  }

  function setLanguage(lang) {
    if (lang !== 'en' && lang !== 'kn') return;
    currentLang = lang;
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {}

    document.documentElement.lang = lang;
    applyTranslations();

    // Dispatch custom event for dynamic components
    const event = new CustomEvent('civiclens-language-changed', {
      detail: { language: lang }
    });
    window.dispatchEvent(event);
  }

  function getLanguage() {
    return currentLang;
  }

  function applyTranslations() {
    // 1. Text content
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) {
        el.textContent = t(key);
      }
    });

    // 2. HTML content
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
      const key = el.getAttribute('data-i18n-html');
      if (key) {
        el.innerHTML = t(key);
      }
    });

    // 3. Placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) {
        el.placeholder = t(key);
      }
    });

    // 4. Update language toggle pills if present
    document.querySelectorAll('.cl-lang-pill').forEach(pill => {
      const pLang = pill.getAttribute('data-lang');
      pill.classList.toggle('active', pLang === currentLang);
    });
  }

  // Auto-initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    t: t,
    getLanguage: getLanguage,
    setLanguage: setLanguage,
    applyTranslations: applyTranslations,
    DICTIONARY: DICTIONARY,
  };
}));

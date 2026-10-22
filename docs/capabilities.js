'use strict';
function auditMatches(entry, filters) {
  const query = (filters.query || '').toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const search = (entry.search || '').toLocaleLowerCase();
  return query.every(word => search.includes(word)) &&
    ['area', 'stage', 'kind', 'origin', 'priority'].every(key => !filters[key] || entry[key] === filters[key]);
}

if (typeof document !== 'undefined') {
  const form = document.getElementById('filters');
  const cards = [...document.querySelectorAll('[data-entry]')];
  const results = document.getElementById('results');
  const empty = document.getElementById('empty');
  function applyFilters() {
    const filters = Object.fromEntries(new FormData(form));
    let visible = 0;
    for (const card of cards) {
      const matches = auditMatches(card.dataset, filters);
      card.hidden = !matches;
      if (matches) visible++;
    }
    results.textContent = `${visible} of ${cards.length} audit entries. Sorted by priority, then area.`;
    empty.hidden = visible !== 0;
  }
  form.hidden = false;
  form.addEventListener('input', applyFilters);
  form.addEventListener('change', applyFilters);
  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('reset', () => setTimeout(applyFilters, 0));
  // Evidence/iteration links must still reach an entry hidden by current filters.
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="#"]');
    const card = link && document.getElementById(link.getAttribute('href').slice(1));
    if (card?.hasAttribute('data-entry') && card.hidden) {
      form.reset();
      applyFilters();
    }
  });
  applyFilters();
}

if (typeof module !== 'undefined') module.exports = {auditMatches};

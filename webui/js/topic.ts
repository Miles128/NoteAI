

var _pendingDragData: { filePath: string | null; cardEl: Element | null } = { filePath: null, cardEl: null };



function loadTopicPendingPanel(pending: any[], topicNames?: string[]) {
    topicNames = topicNames || [];
    var panel = document.getElementById('topic-pending-panel');
    if (!panel) return;

    if (!pending || pending.length === 0) {
        panel.style.display = 'none';
        return;
    }

    var html = '<div class="topic-pending-header">' + window.t('topic.pendingHeader') + ' <span class="topic-pending-count">' + pending.length + '</span></div>';
    html += '<div class="topic-pending-hint">' + window.t('topic.dragToFolderHint') + '</div>';
    html += '<div class="topic-pending-list">';

    pending.forEach(function(p, i) {
        html += '<div class="topic-pending-card" draggable="true" data-file="' + window.escapeAttr(p.file) + '" data-index="' + i + '">';
        html += '<div class="topic-pending-filename">' + window.escapeHtml(p.title || p.file) + '</div>';
        html += '<div class="topic-pending-candidates">';
        (p.candidates || []).forEach(function(c: string) {
            html += '<button class="topic-candidate-btn" data-topic="' + window.escapeAttr(c) + '" data-file="' + window.escapeAttr(p.file) + '" onclick="onCandidateClick(this)">' + window.escapeHtml(c) + '</button>';
        });
        html += '</div>';
        html += '</div>';
    });

    html += '</div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.topic-custom-input').forEach(function(input) {
        var inputEl = input as HTMLInputElement;
        inputEl.addEventListener('keydown', function(e: KeyboardEvent) {
            if (e.key === 'Enter') {
                onInputEnter(inputEl);
            }
        });
        inputEl.addEventListener('input', function() {
            onInputChange(inputEl);
        });
    });

    setupPendingCardDragDrop(panel);
}

function setupPendingCardDragDrop(panel: HTMLElement) {
    panel.addEventListener('dragstart', function(e: DragEvent) {
        var card = (e.target as Element).closest('.topic-pending-card');
        if (!card) return;
        if (card.classList.contains('resolving') || card.classList.contains('resolved')) return;

        var filePath = card.getAttribute('data-file');
        if (!filePath) return;

        _pendingDragData.filePath = filePath;
        _pendingDragData.cardEl = card;
        card.classList.add('dragging');

        e.dataTransfer!.effectAllowed = 'move';
        e.dataTransfer!.setData('text/plain', filePath);
    });

    panel.addEventListener('dragend', function(e: DragEvent) {
        var card = (e.target as Element).closest('.topic-pending-card');
        if (card) card.classList.remove('dragging');
        _pendingDragData.filePath = null;
        _pendingDragData.cardEl = null;
    });
}

function onCandidateClick(btnEl: HTMLElement) {
    var card = btnEl.closest('.topic-pending-card') as HTMLElement | null;
    if (!card) return;

    var btns = card.querySelectorAll('.topic-candidate-btn');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
    btnEl.classList.add('topic-candidate-selected');

    // A candidate is an explicit user choice. Apply it immediately; drag/drop
    // onto the folder tree remains the second direct-manipulation path.
    doConfirmTopic(card);
}

function onInputChange(inputEl: HTMLInputElement) {
    var card = inputEl.closest('.topic-pending-card');
    if (!card) return;
    var btns = card.querySelectorAll('.topic-candidate-btn.topic-candidate-selected');
    btns.forEach(function(b) { b.classList.remove('topic-candidate-selected'); });
}

function onInputEnter(inputEl: HTMLInputElement) {
    var card = inputEl.closest('.topic-pending-card') as HTMLElement | null;
    if (!card) return;
    doConfirmTopic(card);
}

function doConfirmTopic(cardEl: HTMLElement) {
    if (cardEl.classList.contains('resolving')) return;

    var file = cardEl.getAttribute('data-file');
    if (!file) return;

    var input = cardEl.querySelector('.topic-custom-input') as HTMLInputElement | null;
    var custom = (input && input.value) ? input.value.trim() : '';

    // Also read from the <select> dropdown
    var selectEl = cardEl.querySelector('.topic-select') as HTMLSelectElement | null;
    var selectVal = (selectEl && selectEl.value) ? selectEl.value : '';

    var selectedBtn = cardEl.querySelector('.topic-candidate-btn.topic-candidate-selected');
    var selectedTopic = selectedBtn ? selectedBtn.getAttribute('data-topic') || '' : '';

    var topic = custom || selectVal || selectedTopic;
    if (!topic) return;

    var btns = cardEl.querySelectorAll('.topic-candidate-btn');
    var customBtn = cardEl.querySelector('.topic-custom-btn') as HTMLButtonElement | null;

    btns.forEach(function(b) {
        if (b.getAttribute('data-topic') === topic) {
            b.classList.add('topic-candidate-selected');
        } else {
            b.classList.add('topic-candidate-disabled');
        }
    });

    if (input) input.disabled = true;
    if (selectEl) selectEl.disabled = true;
    if (customBtn) customBtn.disabled = true;
    cardEl.classList.add('resolving');

    window.api.resolveTopic(file, topic).then(function(result) {
        if (result && result.success) {
            cardEl.classList.add('resolved');
            animateCardOut(cardEl);
        } else {
            cardEl.classList.remove('resolving');
            btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
            if (input) input.disabled = false;
            if (selectEl) selectEl.disabled = false;
            if (customBtn) customBtn.disabled = false;
            alert(window.t('topic.confirmTopicFailed') + (result ? result.message : window.t('common.unknownError')));
        }
    }).catch(function(e) {
        console.error('[Topic] resolve error:', e);
        cardEl.classList.remove('resolving');
        btns.forEach(function(b) { b.classList.remove('topic-candidate-disabled'); });
        if (input) input.disabled = false;
        if (selectEl) selectEl.disabled = false;
        if (customBtn) customBtn.disabled = false;
        alert(window.t('topic.confirmTopicFailed') + ((e as Error).message || window.t('common.errorOccurred')));
    });
}

function animateCardOut(cardEl: HTMLElement) {
    cardEl.style.transition = 'opacity 0.3s ease, transform 0.3s ease, margin 0.3s ease, padding 0.3s ease, min-height 0.3s ease';
    cardEl.style.opacity = '0';
    cardEl.style.transform = 'translateY(-20px) scale(0.96)';
    cardEl.style.marginTop = '0';
    cardEl.style.marginBottom = '0';
    cardEl.style.paddingTop = '0';
    cardEl.style.paddingBottom = '0';
    cardEl.style.minHeight = '0';
    cardEl.style.overflow = 'hidden';

    setTimeout(function() {
        var list = cardEl.parentElement;
        if (list && list.classList && list.classList.contains('topic-pending-list')) {
            cardEl.remove();
            var remaining = list.querySelectorAll('.topic-pending-card:not(.resolved)').length;
            var countEl = list.parentElement && list.parentElement.querySelector('.topic-pending-count');
            if (countEl) countEl.textContent = String(remaining);
            if (remaining === 0) {
                var pendingPanel = document.getElementById('topic-pending-panel');
                if (pendingPanel) pendingPanel.style.display = 'none';
            }
        }
    }, 350);
}

function hasTopicPending(): boolean {
    var panel = document.getElementById('topic-pending-panel');
    if (!panel) return false;
    var cards = panel.querySelectorAll('.topic-pending-card:not(.resolved)');
    return cards.length > 0;
}

window.loadTopicPendingPanel = loadTopicPendingPanel;
window.onCandidateClick = onCandidateClick;
window.hasTopicPending = hasTopicPending;



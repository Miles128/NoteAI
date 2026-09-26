/** 共享保存通道：保存 UI 配置片段并反馈状态。 */

// ---------------------------------------------------------------------------
// 共享保存通道（保存 UI 配置片段并反馈状态）
// ---------------------------------------------------------------------------

export async function saveAssistantUiConfig(partial: any) {
    try {
        // 走 state 门面而非裸 api：门面会把改动并进 uiConfig 缓存，
        // 否则本次会话内读到的仍是保存前的旧值。
        var result = window.state && window.state.saveUiConfig
            ? await window.state.saveUiConfig(partial)
            : await window.api.saveUiConfig(partial);
        if (result && result.success) {
            window.updateStatus(window.t('settings.autoSaved'));
        } else {
            window.updateStatus(window.t('settings.autoSaveFailed', {
                message: (result && result.message) || window.t('common.unknownError'),
            }));
        }
        return result;
    } catch (e) {
        console.error('[Settings] save assistant config error:', e);
        return null;
    }
}

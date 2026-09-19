/** 共享保存通道：保存 UI 配置片段并反馈状态。 */

// ---------------------------------------------------------------------------
// 共享保存通道（保存 UI 配置片段并反馈状态）
// ---------------------------------------------------------------------------

export async function saveAssistantUiConfig(partial: any) {
    try {
        var result = await window.api.saveUiConfig(partial);
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

// ================================================================
// Storage - 统一的 localStorage 抽象层
// 提供类型安全、错误处理完善的存储 API
// ================================================================

(function() {
    'use strict';

    var Storage = {
        // 存储键名常量，集中管理避免冲突
        KEYS: {
            GRAPH_LAYOUT: 'noteai.graphLayout.v2',
            THEME: 'noteai_theme',
            DOWNLOADER_CONFIG: 'downloader-config',
            CONVERTER_CONFIG: 'converter-config',
            TREE_STATE: 'tree-expanded-state',
            TREE_SHOW_FILE_COUNT: 'noteai.treeShowFileCount',
            SIDEBAR_WIDTH: 'sidebar-width',
            FONT_SIZE: 'noteai_font_size'
        },

        /**
         * 保存值到 localStorage（JSON 序列化）
         * @param {string} key - 存储键
         * @param {*} value - 要存储的值
         * @param {Object} [options] - 选项
         * @param {boolean} [options.silent=false] - 是否静默失败
         * @returns {boolean} 是否保存成功
         */
        setItem: function(key, value, options) {
            options = options || {};
            try {
                var serialized = JSON.stringify(value);
                localStorage.setItem(key, serialized);
                return true;
            } catch (e) {
                if (!options.silent) {
                    console.warn('[Storage] Failed to save item:', key, e);
                }
                return false;
            }
        },

        /**
         * 从 localStorage 读取值（JSON 反序列化）
         * @param {string} key - 存储键
         * @param {*} [defaultValue] - 默认值
         * @param {Object} [options] - 选项
         * @param {boolean} [options.silent=false] - 是否静默失败
         * @returns {*} 存储的值或默认值
         */
        getItem: function(key, defaultValue, options) {
            options = options || {};
            try {
                var raw = localStorage.getItem(key);
                if (raw === null) {
                    return defaultValue;
                }
                return JSON.parse(raw);
            } catch (e) {
                if (!options.silent) {
                    console.warn('[Storage] Failed to load item:', key, e);
                }
                return defaultValue;
            }
        },

        /**
         * 保存原始字符串到 localStorage（不进行 JSON 序列化）
         * 用于向后兼容已存在的非 JSON 存储
         * @param {string} key - 存储键
         * @param {string} value - 原始字符串
         * @param {Object} [options] - 选项
         * @param {boolean} [options.silent=false] - 是否静默失败
         * @returns {boolean} 是否保存成功
         */
        setRaw: function(key, value, options) {
            options = options || {};
            try {
                localStorage.setItem(key, value);
                return true;
            } catch (e) {
                if (!options.silent) {
                    console.warn('[Storage] Failed to save raw item:', key, e);
                }
                return false;
            }
        },

        /**
         * 从 localStorage 读取原始字符串（不进行 JSON 反序列化）
         * @param {string} key - 存储键
         * @param {string} [defaultValue] - 默认值
         * @param {Object} [options] - 选项
         * @param {boolean} [options.silent=false] - 是否静默失败
         * @returns {string} 存储的原始字符串或默认值
         */
        getRaw: function(key, defaultValue, options) {
            options = options || {};
            try {
                var raw = localStorage.getItem(key);
                if (raw === null) {
                    return defaultValue;
                }
                return raw;
            } catch (e) {
                if (!options.silent) {
                    console.warn('[Storage] Failed to load raw item:', key, e);
                }
                return defaultValue;
            }
        },

        /**
         * 删除指定键
         * @param {string} key - 存储键
         * @param {Object} [options] - 选项
         * @param {boolean} [options.silent=false] - 是否静默失败
         * @returns {boolean} 是否删除成功
         */
        removeItem: function(key, options) {
            options = options || {};
            try {
                localStorage.removeItem(key);
                return true;
            } catch (e) {
                if (!options.silent) {
                    console.warn('[Storage] Failed to remove item:', key, e);
                }
                return false;
            }
        },

        /**
         * 清空所有应用相关的存储
         * @param {Object} [options] - 选项
         * @param {boolean} [options.silent=false] - 是否静默失败
         * @returns {boolean} 是否全部清空成功
         */
        clearAppStorage: function(options) {
            options = options || {};
            var success = true;
            var self = this;
            Object.keys(this.KEYS).forEach(function(k) {
                if (!self.removeItem(self.KEYS[k], { silent: true })) {
                    success = false;
                }
            });
            if (!success && !options.silent) {
                console.warn('[Storage] Some items failed to clear');
            }
            return success;
        }
    };

    window.Storage = Storage;
})();

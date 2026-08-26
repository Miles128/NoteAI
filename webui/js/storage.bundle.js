"use strict";
(() => {
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __commonJS = (cb, mod) => function __require() {
    try {
      return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
    } catch (e) {
      throw mod = 0, e;
    }
  };

  // webui/js/storage.ts
  var require_storage = __commonJS({
    "webui/js/storage.ts"() {
      (function() {
        "use strict";
        var StorageImpl = {
          // 存储键名常量，集中管理避免冲突
          KEYS: {
            GRAPH_LAYOUT: "noteai.graphLayout.v2",
            GRAPH_LAYOUT_MODE: "noteai.graphLayoutMode.v1",
            THEME: "noteai_theme",
            ACCENT_COLOR: "noteai_accent_color",
            DOWNLOADER_CONFIG: "downloader-config",
            CONVERTER_CONFIG: "converter-config",
            TREE_STATE: "tree-expanded-state",
            TREE_SHOW_FILE_COUNT: "noteai.treeShowFileCount",
            SIDEBAR_WIDTH: "sidebar-width",
            FONT_SIZE: "noteai_font_size"
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
                console.warn("[Storage] Failed to save item:", key, e);
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
                console.warn("[Storage] Failed to load item:", key, e);
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
                console.warn("[Storage] Failed to save raw item:", key, e);
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
                console.warn("[Storage] Failed to load raw item:", key, e);
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
                console.warn("[Storage] Failed to remove item:", key, e);
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
              console.warn("[Storage] Some items failed to clear");
            }
            return success;
          }
        };
        window.Storage = StorageImpl;
      })();
    }
  });
  require_storage();
})();
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsic3RvcmFnZS50cyJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuLy8gU3RvcmFnZSAtIFx1N0VERlx1NEUwMFx1NzY4NCBsb2NhbFN0b3JhZ2UgXHU2MkJEXHU4QzYxXHU1QzQyXHVGRjA4XHU0RUNFIHN0b3JhZ2UuanMgXHU2RTEwXHU4RkRCXHU4RkMxXHU3OUZCXHU1MjMwIFRTXHVGRjA5XG4vLyBcdTYzRDBcdTRGOUJcdTdDN0JcdTU3OEJcdTVCODlcdTUxNjhcdTMwMDFcdTk1MTlcdThCRUZcdTU5MDRcdTc0MDZcdTVCOENcdTU1ODRcdTc2ODRcdTVCNThcdTUwQTggQVBJXG4vLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG5cbihmdW5jdGlvbigpIHtcbiAgICAndXNlIHN0cmljdCc7XG5cbiAgICBpbnRlcmZhY2UgU3RvcmFnZU9wdHMge1xuICAgICAgICBzaWxlbnQ/OiBib29sZWFuO1xuICAgIH1cblxuICAgIHZhciBTdG9yYWdlSW1wbCA9IHtcbiAgICAgICAgLy8gXHU1QjU4XHU1MEE4XHU5NTJFXHU1NDBEXHU1RTM4XHU5MUNGXHVGRjBDXHU5NkM2XHU0RTJEXHU3QkExXHU3NDA2XHU5MDdGXHU1MTREXHU1MUIyXHU3QTgxXG4gICAgICAgIEtFWVM6IHtcbiAgICAgICAgICAgIEdSQVBIX0xBWU9VVDogJ25vdGVhaS5ncmFwaExheW91dC52MicsXG4gICAgICAgICAgICBHUkFQSF9MQVlPVVRfTU9ERTogJ25vdGVhaS5ncmFwaExheW91dE1vZGUudjEnLFxuICAgICAgICAgICAgVEhFTUU6ICdub3RlYWlfdGhlbWUnLFxuICAgICAgICAgICAgQUNDRU5UX0NPTE9SOiAnbm90ZWFpX2FjY2VudF9jb2xvcicsXG4gICAgICAgICAgICBET1dOTE9BREVSX0NPTkZJRzogJ2Rvd25sb2FkZXItY29uZmlnJyxcbiAgICAgICAgICAgIENPTlZFUlRFUl9DT05GSUc6ICdjb252ZXJ0ZXItY29uZmlnJyxcbiAgICAgICAgICAgIFRSRUVfU1RBVEU6ICd0cmVlLWV4cGFuZGVkLXN0YXRlJyxcbiAgICAgICAgICAgIFRSRUVfU0hPV19GSUxFX0NPVU5UOiAnbm90ZWFpLnRyZWVTaG93RmlsZUNvdW50JyxcbiAgICAgICAgICAgIFNJREVCQVJfV0lEVEg6ICdzaWRlYmFyLXdpZHRoJyxcbiAgICAgICAgICAgIEZPTlRfU0laRTogJ25vdGVhaV9mb250X3NpemUnXG4gICAgICAgIH0gYXMgU3RvcmFnZUtleXMsXG5cbiAgICAgICAgLyoqXG4gICAgICAgICAqIFx1NEZERFx1NUI1OFx1NTAzQ1x1NTIzMCBsb2NhbFN0b3JhZ2VcdUZGMDhKU09OIFx1NUU4Rlx1NTIxN1x1NTMxNlx1RkYwOVxuICAgICAgICAgKiBAcGFyYW0ge3N0cmluZ30ga2V5IC0gXHU1QjU4XHU1MEE4XHU5NTJFXG4gICAgICAgICAqIEBwYXJhbSB7Kn0gdmFsdWUgLSBcdTg5ODFcdTVCNThcdTUwQThcdTc2ODRcdTUwM0NcbiAgICAgICAgICogQHBhcmFtIHtPYmplY3R9IFtvcHRpb25zXSAtIFx1OTAwOVx1OTg3OVxuICAgICAgICAgKiBAcGFyYW0ge2Jvb2xlYW59IFtvcHRpb25zLnNpbGVudD1mYWxzZV0gLSBcdTY2MkZcdTU0MjZcdTk3NTlcdTlFRDhcdTU5MzFcdThEMjVcbiAgICAgICAgICogQHJldHVybnMge2Jvb2xlYW59IFx1NjYyRlx1NTQyNlx1NEZERFx1NUI1OFx1NjIxMFx1NTI5RlxuICAgICAgICAgKi9cbiAgICAgICAgc2V0SXRlbTogZnVuY3Rpb24oa2V5OiBzdHJpbmcsIHZhbHVlOiB1bmtub3duLCBvcHRpb25zPzogU3RvcmFnZU9wdHMpOiBib29sZWFuIHtcbiAgICAgICAgICAgIG9wdGlvbnMgPSBvcHRpb25zIHx8IHt9O1xuICAgICAgICAgICAgdHJ5IHtcbiAgICAgICAgICAgICAgICB2YXIgc2VyaWFsaXplZCA9IEpTT04uc3RyaW5naWZ5KHZhbHVlKTtcbiAgICAgICAgICAgICAgICBsb2NhbFN0b3JhZ2Uuc2V0SXRlbShrZXksIHNlcmlhbGl6ZWQpO1xuICAgICAgICAgICAgICAgIHJldHVybiB0cnVlO1xuICAgICAgICAgICAgfSBjYXRjaCAoZSkge1xuICAgICAgICAgICAgICAgIGlmICghb3B0aW9ucy5zaWxlbnQpIHtcbiAgICAgICAgICAgICAgICAgICAgY29uc29sZS53YXJuKCdbU3RvcmFnZV0gRmFpbGVkIHRvIHNhdmUgaXRlbTonLCBrZXksIGUpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICByZXR1cm4gZmFsc2U7XG4gICAgICAgICAgICB9XG4gICAgICAgIH0sXG5cbiAgICAgICAgLyoqXG4gICAgICAgICAqIFx1NEVDRSBsb2NhbFN0b3JhZ2UgXHU4QkZCXHU1M0Q2XHU1MDNDXHVGRjA4SlNPTiBcdTUzQ0RcdTVFOEZcdTUyMTdcdTUzMTZcdUZGMDlcbiAgICAgICAgICogQHBhcmFtIHtzdHJpbmd9IGtleSAtIFx1NUI1OFx1NTBBOFx1OTUyRVxuICAgICAgICAgKiBAcGFyYW0geyp9IFtkZWZhdWx0VmFsdWVdIC0gXHU5RUQ4XHU4QkE0XHU1MDNDXG4gICAgICAgICAqIEBwYXJhbSB7T2JqZWN0fSBbb3B0aW9uc10gLSBcdTkwMDlcdTk4NzlcbiAgICAgICAgICogQHBhcmFtIHtib29sZWFufSBbb3B0aW9ucy5zaWxlbnQ9ZmFsc2VdIC0gXHU2NjJGXHU1NDI2XHU5NzU5XHU5RUQ4XHU1OTMxXHU4RDI1XG4gICAgICAgICAqIEByZXR1cm5zIHsqfSBcdTVCNThcdTUwQThcdTc2ODRcdTUwM0NcdTYyMTZcdTlFRDhcdThCQTRcdTUwM0NcbiAgICAgICAgICovXG4gICAgICAgIGdldEl0ZW06IGZ1bmN0aW9uPFQ+KGtleTogc3RyaW5nLCBkZWZhdWx0VmFsdWU/OiBULCBvcHRpb25zPzogU3RvcmFnZU9wdHMpOiBUIHtcbiAgICAgICAgICAgIG9wdGlvbnMgPSBvcHRpb25zIHx8IHt9O1xuICAgICAgICAgICAgdHJ5IHtcbiAgICAgICAgICAgICAgICB2YXIgcmF3ID0gbG9jYWxTdG9yYWdlLmdldEl0ZW0oa2V5KTtcbiAgICAgICAgICAgICAgICBpZiAocmF3ID09PSBudWxsKSB7XG4gICAgICAgICAgICAgICAgICAgIHJldHVybiBkZWZhdWx0VmFsdWUgYXMgVDtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgcmV0dXJuIEpTT04ucGFyc2UocmF3KSBhcyBUO1xuICAgICAgICAgICAgfSBjYXRjaCAoZSkge1xuICAgICAgICAgICAgICAgIGlmICghb3B0aW9ucy5zaWxlbnQpIHtcbiAgICAgICAgICAgICAgICAgICAgY29uc29sZS53YXJuKCdbU3RvcmFnZV0gRmFpbGVkIHRvIGxvYWQgaXRlbTonLCBrZXksIGUpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICByZXR1cm4gZGVmYXVsdFZhbHVlIGFzIFQ7XG4gICAgICAgICAgICB9XG4gICAgICAgIH0sXG5cbiAgICAgICAgLyoqXG4gICAgICAgICAqIFx1NEZERFx1NUI1OFx1NTM5Rlx1NTlDQlx1NUI1N1x1N0IyNlx1NEUzMlx1NTIzMCBsb2NhbFN0b3JhZ2VcdUZGMDhcdTRFMERcdThGREJcdTg4NEMgSlNPTiBcdTVFOEZcdTUyMTdcdTUzMTZcdUZGMDlcbiAgICAgICAgICogXHU3NTI4XHU0RThFXHU1NDExXHU1NDBFXHU1MTdDXHU1QkI5XHU1REYyXHU1QjU4XHU1NzI4XHU3Njg0XHU5NzVFIEpTT04gXHU1QjU4XHU1MEE4XG4gICAgICAgICAqIEBwYXJhbSB7c3RyaW5nfSBrZXkgLSBcdTVCNThcdTUwQThcdTk1MkVcbiAgICAgICAgICogQHBhcmFtIHtzdHJpbmd9IHZhbHVlIC0gXHU1MzlGXHU1OUNCXHU1QjU3XHU3QjI2XHU0RTMyXG4gICAgICAgICAqIEBwYXJhbSB7T2JqZWN0fSBbb3B0aW9uc10gLSBcdTkwMDlcdTk4NzlcbiAgICAgICAgICogQHBhcmFtIHtib29sZWFufSBbb3B0aW9ucy5zaWxlbnQ9ZmFsc2VdIC0gXHU2NjJGXHU1NDI2XHU5NzU5XHU5RUQ4XHU1OTMxXHU4RDI1XG4gICAgICAgICAqIEByZXR1cm5zIHtib29sZWFufSBcdTY2MkZcdTU0MjZcdTRGRERcdTVCNThcdTYyMTBcdTUyOUZcbiAgICAgICAgICovXG4gICAgICAgIHNldFJhdzogZnVuY3Rpb24oa2V5OiBzdHJpbmcsIHZhbHVlOiB1bmtub3duLCBvcHRpb25zPzogU3RvcmFnZU9wdHMpOiBib29sZWFuIHtcbiAgICAgICAgICAgIG9wdGlvbnMgPSBvcHRpb25zIHx8IHt9O1xuICAgICAgICAgICAgdHJ5IHtcbiAgICAgICAgICAgICAgICBsb2NhbFN0b3JhZ2Uuc2V0SXRlbShrZXksIHZhbHVlIGFzIHN0cmluZyk7XG4gICAgICAgICAgICAgICAgcmV0dXJuIHRydWU7XG4gICAgICAgICAgICB9IGNhdGNoIChlKSB7XG4gICAgICAgICAgICAgICAgaWYgKCFvcHRpb25zLnNpbGVudCkge1xuICAgICAgICAgICAgICAgICAgICBjb25zb2xlLndhcm4oJ1tTdG9yYWdlXSBGYWlsZWQgdG8gc2F2ZSByYXcgaXRlbTonLCBrZXksIGUpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICByZXR1cm4gZmFsc2U7XG4gICAgICAgICAgICB9XG4gICAgICAgIH0sXG5cbiAgICAgICAgLyoqXG4gICAgICAgICAqIFx1NEVDRSBsb2NhbFN0b3JhZ2UgXHU4QkZCXHU1M0Q2XHU1MzlGXHU1OUNCXHU1QjU3XHU3QjI2XHU0RTMyXHVGRjA4XHU0RTBEXHU4RkRCXHU4ODRDIEpTT04gXHU1M0NEXHU1RThGXHU1MjE3XHU1MzE2XHVGRjA5XG4gICAgICAgICAqIEBwYXJhbSB7c3RyaW5nfSBrZXkgLSBcdTVCNThcdTUwQThcdTk1MkVcbiAgICAgICAgICogQHBhcmFtIHtzdHJpbmd9IFtkZWZhdWx0VmFsdWVdIC0gXHU5RUQ4XHU4QkE0XHU1MDNDXG4gICAgICAgICAqIEBwYXJhbSB7T2JqZWN0fSBbb3B0aW9uc10gLSBcdTkwMDlcdTk4NzlcbiAgICAgICAgICogQHBhcmFtIHtib29sZWFufSBbb3B0aW9ucy5zaWxlbnQ9ZmFsc2VdIC0gXHU2NjJGXHU1NDI2XHU5NzU5XHU5RUQ4XHU1OTMxXHU4RDI1XG4gICAgICAgICAqIEByZXR1cm5zIHtzdHJpbmd9IFx1NUI1OFx1NTBBOFx1NzY4NFx1NTM5Rlx1NTlDQlx1NUI1N1x1N0IyNlx1NEUzMlx1NjIxNlx1OUVEOFx1OEJBNFx1NTAzQ1xuICAgICAgICAgKi9cbiAgICAgICAgZ2V0UmF3OiBmdW5jdGlvbihrZXk6IHN0cmluZywgZGVmYXVsdFZhbHVlPzogdW5rbm93biwgb3B0aW9ucz86IFN0b3JhZ2VPcHRzKTogdW5rbm93biB7XG4gICAgICAgICAgICBvcHRpb25zID0gb3B0aW9ucyB8fCB7fTtcbiAgICAgICAgICAgIHRyeSB7XG4gICAgICAgICAgICAgICAgdmFyIHJhdyA9IGxvY2FsU3RvcmFnZS5nZXRJdGVtKGtleSk7XG4gICAgICAgICAgICAgICAgaWYgKHJhdyA9PT0gbnVsbCkge1xuICAgICAgICAgICAgICAgICAgICByZXR1cm4gZGVmYXVsdFZhbHVlO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICByZXR1cm4gcmF3O1xuICAgICAgICAgICAgfSBjYXRjaCAoZSkge1xuICAgICAgICAgICAgICAgIGlmICghb3B0aW9ucy5zaWxlbnQpIHtcbiAgICAgICAgICAgICAgICAgICAgY29uc29sZS53YXJuKCdbU3RvcmFnZV0gRmFpbGVkIHRvIGxvYWQgcmF3IGl0ZW06Jywga2V5LCBlKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgcmV0dXJuIGRlZmF1bHRWYWx1ZTtcbiAgICAgICAgICAgIH1cbiAgICAgICAgfSxcblxuICAgICAgICAvKipcbiAgICAgICAgICogXHU1MjIwXHU5NjY0XHU2MzA3XHU1QjlBXHU5NTJFXG4gICAgICAgICAqIEBwYXJhbSB7c3RyaW5nfSBrZXkgLSBcdTVCNThcdTUwQThcdTk1MkVcbiAgICAgICAgICogQHBhcmFtIHtPYmplY3R9IFtvcHRpb25zXSAtIFx1OTAwOVx1OTg3OVxuICAgICAgICAgKiBAcGFyYW0ge2Jvb2xlYW59IFtvcHRpb25zLnNpbGVudD1mYWxzZV0gLSBcdTY2MkZcdTU0MjZcdTk3NTlcdTlFRDhcdTU5MzFcdThEMjVcbiAgICAgICAgICogQHJldHVybnMge2Jvb2xlYW59IFx1NjYyRlx1NTQyNlx1NTIyMFx1OTY2NFx1NjIxMFx1NTI5RlxuICAgICAgICAgKi9cbiAgICAgICAgcmVtb3ZlSXRlbTogZnVuY3Rpb24oa2V5OiBzdHJpbmcsIG9wdGlvbnM/OiBTdG9yYWdlT3B0cyk6IGJvb2xlYW4ge1xuICAgICAgICAgICAgb3B0aW9ucyA9IG9wdGlvbnMgfHwge307XG4gICAgICAgICAgICB0cnkge1xuICAgICAgICAgICAgICAgIGxvY2FsU3RvcmFnZS5yZW1vdmVJdGVtKGtleSk7XG4gICAgICAgICAgICAgICAgcmV0dXJuIHRydWU7XG4gICAgICAgICAgICB9IGNhdGNoIChlKSB7XG4gICAgICAgICAgICAgICAgaWYgKCFvcHRpb25zLnNpbGVudCkge1xuICAgICAgICAgICAgICAgICAgICBjb25zb2xlLndhcm4oJ1tTdG9yYWdlXSBGYWlsZWQgdG8gcmVtb3ZlIGl0ZW06Jywga2V5LCBlKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgICAgcmV0dXJuIGZhbHNlO1xuICAgICAgICAgICAgfVxuICAgICAgICB9LFxuXG4gICAgICAgIC8qKlxuICAgICAgICAgKiBcdTZFMDVcdTdBN0FcdTYyNDBcdTY3MDlcdTVFOTRcdTc1MjhcdTc2RjhcdTUxNzNcdTc2ODRcdTVCNThcdTUwQThcbiAgICAgICAgICogQHBhcmFtIHtPYmplY3R9IFtvcHRpb25zXSAtIFx1OTAwOVx1OTg3OVxuICAgICAgICAgKiBAcGFyYW0ge2Jvb2xlYW59IFtvcHRpb25zLnNpbGVudD1mYWxzZV0gLSBcdTY2MkZcdTU0MjZcdTk3NTlcdTlFRDhcdTU5MzFcdThEMjVcbiAgICAgICAgICogQHJldHVybnMge2Jvb2xlYW59IFx1NjYyRlx1NTQyNlx1NTE2OFx1OTBFOFx1NkUwNVx1N0E3QVx1NjIxMFx1NTI5RlxuICAgICAgICAgKi9cbiAgICAgICAgY2xlYXJBcHBTdG9yYWdlOiBmdW5jdGlvbihvcHRpb25zPzogU3RvcmFnZU9wdHMpOiBib29sZWFuIHtcbiAgICAgICAgICAgIG9wdGlvbnMgPSBvcHRpb25zIHx8IHt9O1xuICAgICAgICAgICAgdmFyIHN1Y2Nlc3MgPSB0cnVlO1xuICAgICAgICAgICAgdmFyIHNlbGY6IFN0b3JhZ2VNb2R1bGUgPSB0aGlzO1xuICAgICAgICAgICAgT2JqZWN0LmtleXModGhpcy5LRVlTKS5mb3JFYWNoKGZ1bmN0aW9uKGspIHtcbiAgICAgICAgICAgICAgICBpZiAoIXNlbGYucmVtb3ZlSXRlbShzZWxmLktFWVNbayBhcyBrZXlvZiBTdG9yYWdlS2V5c10sIHsgc2lsZW50OiB0cnVlIH0pKSB7XG4gICAgICAgICAgICAgICAgICAgIHN1Y2Nlc3MgPSBmYWxzZTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIGlmICghc3VjY2VzcyAmJiAhb3B0aW9ucy5zaWxlbnQpIHtcbiAgICAgICAgICAgICAgICBjb25zb2xlLndhcm4oJ1tTdG9yYWdlXSBTb21lIGl0ZW1zIGZhaWxlZCB0byBjbGVhcicpO1xuICAgICAgICAgICAgfVxuICAgICAgICAgICAgcmV0dXJuIHN1Y2Nlc3M7XG4gICAgICAgIH1cbiAgICB9O1xuXG4gICAgd2luZG93LlN0b3JhZ2UgPSBTdG9yYWdlSW1wbCBhcyBhbnk7XG59KSgpOyJdLAogICJtYXBwaW5ncyI6ICI7Ozs7Ozs7Ozs7OztBQUFBO0FBQUE7QUFLQSxPQUFDLFdBQVc7QUFDUjtBQU1BLFlBQUksY0FBYztBQUFBO0FBQUEsVUFFZCxNQUFNO0FBQUEsWUFDRixjQUFjO0FBQUEsWUFDZCxtQkFBbUI7QUFBQSxZQUNuQixPQUFPO0FBQUEsWUFDUCxjQUFjO0FBQUEsWUFDZCxtQkFBbUI7QUFBQSxZQUNuQixrQkFBa0I7QUFBQSxZQUNsQixZQUFZO0FBQUEsWUFDWixzQkFBc0I7QUFBQSxZQUN0QixlQUFlO0FBQUEsWUFDZixXQUFXO0FBQUEsVUFDZjtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQSxVQVVBLFNBQVMsU0FBUyxLQUFhLE9BQWdCLFNBQWdDO0FBQzNFLHNCQUFVLFdBQVcsQ0FBQztBQUN0QixnQkFBSTtBQUNBLGtCQUFJLGFBQWEsS0FBSyxVQUFVLEtBQUs7QUFDckMsMkJBQWEsUUFBUSxLQUFLLFVBQVU7QUFDcEMscUJBQU87QUFBQSxZQUNYLFNBQVMsR0FBRztBQUNSLGtCQUFJLENBQUMsUUFBUSxRQUFRO0FBQ2pCLHdCQUFRLEtBQUssa0NBQWtDLEtBQUssQ0FBQztBQUFBLGNBQ3pEO0FBQ0EscUJBQU87QUFBQSxZQUNYO0FBQUEsVUFDSjtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQSxVQVVBLFNBQVMsU0FBWSxLQUFhLGNBQWtCLFNBQTBCO0FBQzFFLHNCQUFVLFdBQVcsQ0FBQztBQUN0QixnQkFBSTtBQUNBLGtCQUFJLE1BQU0sYUFBYSxRQUFRLEdBQUc7QUFDbEMsa0JBQUksUUFBUSxNQUFNO0FBQ2QsdUJBQU87QUFBQSxjQUNYO0FBQ0EscUJBQU8sS0FBSyxNQUFNLEdBQUc7QUFBQSxZQUN6QixTQUFTLEdBQUc7QUFDUixrQkFBSSxDQUFDLFFBQVEsUUFBUTtBQUNqQix3QkFBUSxLQUFLLGtDQUFrQyxLQUFLLENBQUM7QUFBQSxjQUN6RDtBQUNBLHFCQUFPO0FBQUEsWUFDWDtBQUFBLFVBQ0o7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQSxVQVdBLFFBQVEsU0FBUyxLQUFhLE9BQWdCLFNBQWdDO0FBQzFFLHNCQUFVLFdBQVcsQ0FBQztBQUN0QixnQkFBSTtBQUNBLDJCQUFhLFFBQVEsS0FBSyxLQUFlO0FBQ3pDLHFCQUFPO0FBQUEsWUFDWCxTQUFTLEdBQUc7QUFDUixrQkFBSSxDQUFDLFFBQVEsUUFBUTtBQUNqQix3QkFBUSxLQUFLLHNDQUFzQyxLQUFLLENBQUM7QUFBQSxjQUM3RDtBQUNBLHFCQUFPO0FBQUEsWUFDWDtBQUFBLFVBQ0o7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUEsVUFVQSxRQUFRLFNBQVMsS0FBYSxjQUF3QixTQUFnQztBQUNsRixzQkFBVSxXQUFXLENBQUM7QUFDdEIsZ0JBQUk7QUFDQSxrQkFBSSxNQUFNLGFBQWEsUUFBUSxHQUFHO0FBQ2xDLGtCQUFJLFFBQVEsTUFBTTtBQUNkLHVCQUFPO0FBQUEsY0FDWDtBQUNBLHFCQUFPO0FBQUEsWUFDWCxTQUFTLEdBQUc7QUFDUixrQkFBSSxDQUFDLFFBQVEsUUFBUTtBQUNqQix3QkFBUSxLQUFLLHNDQUFzQyxLQUFLLENBQUM7QUFBQSxjQUM3RDtBQUNBLHFCQUFPO0FBQUEsWUFDWDtBQUFBLFVBQ0o7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBLFVBU0EsWUFBWSxTQUFTLEtBQWEsU0FBZ0M7QUFDOUQsc0JBQVUsV0FBVyxDQUFDO0FBQ3RCLGdCQUFJO0FBQ0EsMkJBQWEsV0FBVyxHQUFHO0FBQzNCLHFCQUFPO0FBQUEsWUFDWCxTQUFTLEdBQUc7QUFDUixrQkFBSSxDQUFDLFFBQVEsUUFBUTtBQUNqQix3QkFBUSxLQUFLLG9DQUFvQyxLQUFLLENBQUM7QUFBQSxjQUMzRDtBQUNBLHFCQUFPO0FBQUEsWUFDWDtBQUFBLFVBQ0o7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQSxVQVFBLGlCQUFpQixTQUFTLFNBQWdDO0FBQ3RELHNCQUFVLFdBQVcsQ0FBQztBQUN0QixnQkFBSSxVQUFVO0FBQ2QsZ0JBQUksT0FBc0I7QUFDMUIsbUJBQU8sS0FBSyxLQUFLLElBQUksRUFBRSxRQUFRLFNBQVMsR0FBRztBQUN2QyxrQkFBSSxDQUFDLEtBQUssV0FBVyxLQUFLLEtBQUssQ0FBc0IsR0FBRyxFQUFFLFFBQVEsS0FBSyxDQUFDLEdBQUc7QUFDdkUsMEJBQVU7QUFBQSxjQUNkO0FBQUEsWUFDSixDQUFDO0FBQ0QsZ0JBQUksQ0FBQyxXQUFXLENBQUMsUUFBUSxRQUFRO0FBQzdCLHNCQUFRLEtBQUssc0NBQXNDO0FBQUEsWUFDdkQ7QUFDQSxtQkFBTztBQUFBLFVBQ1g7QUFBQSxRQUNKO0FBRUEsZUFBTyxVQUFVO0FBQUEsTUFDckIsR0FBRztBQUFBO0FBQUE7IiwKICAibmFtZXMiOiBbXQp9Cg==

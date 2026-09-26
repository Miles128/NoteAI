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

  // webui/js/error-handler.ts
  var require_error_handler = __commonJS({
    "webui/js/error-handler.ts"() {
      (function() {
        "use strict";
        var el = document.getElementById("js-error-panel");
        var log = document.getElementById("js-error-log");
        var errors = [];
        function showErrors() {
          if (!el || !log || errors.length === 0) return;
          el.style.display = "block";
          log.textContent = errors.join("\n\n---\n\n");
        }
        window.onerror = function(msg, url, line, col, err) {
          var info = err && err.stack ? String(err.stack) : String(msg) + " at " + String(url) + ":" + String(line) + ":" + String(col);
          errors.push(info);
          showErrors();
          return false;
        };
        window.addEventListener("unhandledrejection", function(e) {
          var reason = e.reason;
          var info = "Promise rejection: " + (reason && reason.stack ? String(reason.stack) : String(reason));
          errors.push(info);
          showErrors();
        });
        window._customConfirm = function(message) {
          return new Promise(function(resolve) {
            var overlay = document.getElementById("custom-confirm-overlay");
            var msgEl = document.getElementById("custom-confirm-message");
            var okBtn = document.getElementById("custom-confirm-ok");
            var cancelBtn = document.getElementById("custom-confirm-cancel");
            if (!overlay || !msgEl || !okBtn || !cancelBtn) {
              resolve(window.confirm(message));
              return;
            }
            msgEl.textContent = message;
            overlay.style.display = "flex";
            okBtn.focus();
            function cleanup(result) {
              overlay.style.display = "none";
              okBtn.removeEventListener("click", onOk);
              cancelBtn.removeEventListener("click", onCancel);
              resolve(result);
            }
            function onOk() {
              cleanup(true);
            }
            function onCancel() {
              cleanup(false);
            }
            okBtn.addEventListener("click", onOk);
            cancelBtn.addEventListener("click", onCancel);
          });
        };
      })();
    }
  });
  require_error_handler();
})();
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsiZXJyb3ItaGFuZGxlci50cyJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiLyoqXG4gKiBlcnJvci1oYW5kbGVyLnRzIFx1MjAxNFx1MjAxNCBcdTUxNjhcdTVDNDBcdTk1MTlcdThCRUZcdTYzNTVcdTgzQjcgKyBcdTgxRUFcdTVCOUFcdTRFNDlcdTc4NkVcdThCQTRcdTY4NDZcdTMwMDJcbiAqIFx1N0VDRlx1NTE3OFx1ODExQVx1NjcyQ1x1RkYwOGVzYnVpbGQgSUlGRSBidW5kbGVcdUZGMUF3ZWJ1aS9qcy9lcnJvci1oYW5kbGVyLmJ1bmRsZS5qc1x1RkYwOVx1RkYwQ1xuICogXHU1NzI4XHU2QTIxXHU1NzU3XHU4MTFBXHU2NzJDXHU0RTRCXHU1MjREXHU1NDBDXHU2QjY1XHU1MkEwXHU4RjdEXHVGRjBDXHU3ODZFXHU0RkREXHU1QzNEXHU2NUU5XHU1Qjg5XHU4OEM1IG9uZXJyb3IgLyB1bmhhbmRsZWRyZWplY3Rpb25cdTMwMDJcbiAqL1xuKGZ1bmN0aW9uKCkgeyAndXNlIHN0cmljdCc7XG5cbnZhciBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdqcy1lcnJvci1wYW5lbCcpIGFzIEhUTUxFbGVtZW50IHwgbnVsbDtcbnZhciBsb2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnanMtZXJyb3ItbG9nJykgYXMgSFRNTEVsZW1lbnQgfCBudWxsO1xudmFyIGVycm9yczogc3RyaW5nW10gPSBbXTtcblxuZnVuY3Rpb24gc2hvd0Vycm9ycygpIHtcbiAgICBpZiAoIWVsIHx8ICFsb2cgfHwgZXJyb3JzLmxlbmd0aCA9PT0gMCkgcmV0dXJuO1xuICAgIGVsLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snO1xuICAgIGxvZy50ZXh0Q29udGVudCA9IGVycm9ycy5qb2luKCdcXG5cXG4tLS1cXG5cXG4nKTtcbn1cblxud2luZG93Lm9uZXJyb3IgPSBmdW5jdGlvbihtc2c6IHVua25vd24sIHVybDogdW5rbm93biwgbGluZTogdW5rbm93biwgY29sOiB1bmtub3duLCBlcnI6IHVua25vd24pIHtcbiAgICB2YXIgaW5mbyA9IChlcnIgJiYgKGVyciBhcyBFcnJvcikuc3RhY2spXG4gICAgICAgID8gU3RyaW5nKChlcnIgYXMgRXJyb3IpLnN0YWNrKVxuICAgICAgICA6IChTdHJpbmcobXNnKSArICcgYXQgJyArIFN0cmluZyh1cmwpICsgJzonICsgU3RyaW5nKGxpbmUpICsgJzonICsgU3RyaW5nKGNvbCkpO1xuICAgIGVycm9ycy5wdXNoKGluZm8pO1xuICAgIHNob3dFcnJvcnMoKTtcbiAgICByZXR1cm4gZmFsc2U7XG59O1xuXG53aW5kb3cuYWRkRXZlbnRMaXN0ZW5lcigndW5oYW5kbGVkcmVqZWN0aW9uJywgZnVuY3Rpb24oZSkge1xuICAgIHZhciByZWFzb24gPSAoZSBhcyBQcm9taXNlUmVqZWN0aW9uRXZlbnQpLnJlYXNvbjtcbiAgICB2YXIgaW5mbyA9ICdQcm9taXNlIHJlamVjdGlvbjogJyArIChyZWFzb24gJiYgKHJlYXNvbiBhcyBFcnJvcikuc3RhY2sgPyBTdHJpbmcoKHJlYXNvbiBhcyBFcnJvcikuc3RhY2spIDogU3RyaW5nKHJlYXNvbikpO1xuICAgIGVycm9ycy5wdXNoKGluZm8pO1xuICAgIHNob3dFcnJvcnMoKTtcbn0pO1xuXG53aW5kb3cuX2N1c3RvbUNvbmZpcm0gPSBmdW5jdGlvbihtZXNzYWdlOiBzdHJpbmcpOiBQcm9taXNlPGJvb2xlYW4+IHtcbiAgICByZXR1cm4gbmV3IFByb21pc2UoZnVuY3Rpb24ocmVzb2x2ZSkge1xuICAgICAgICB2YXIgb3ZlcmxheSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjdXN0b20tY29uZmlybS1vdmVybGF5JykgYXMgSFRNTEVsZW1lbnQgfCBudWxsO1xuICAgICAgICB2YXIgbXNnRWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3VzdG9tLWNvbmZpcm0tbWVzc2FnZScpIGFzIEhUTUxFbGVtZW50IHwgbnVsbDtcbiAgICAgICAgdmFyIG9rQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2N1c3RvbS1jb25maXJtLW9rJykgYXMgSFRNTEJ1dHRvbkVsZW1lbnQgfCBudWxsO1xuICAgICAgICB2YXIgY2FuY2VsQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2N1c3RvbS1jb25maXJtLWNhbmNlbCcpIGFzIEhUTUxCdXR0b25FbGVtZW50IHwgbnVsbDtcbiAgICAgICAgaWYgKCFvdmVybGF5IHx8ICFtc2dFbCB8fCAhb2tCdG4gfHwgIWNhbmNlbEJ0bikgeyByZXNvbHZlKHdpbmRvdy5jb25maXJtKG1lc3NhZ2UpKTsgcmV0dXJuOyB9XG4gICAgICAgIG1zZ0VsLnRleHRDb250ZW50ID0gbWVzc2FnZTtcbiAgICAgICAgb3ZlcmxheS5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnO1xuICAgICAgICBva0J0bi5mb2N1cygpO1xuICAgICAgICBmdW5jdGlvbiBjbGVhbnVwKHJlc3VsdDogYm9vbGVhbikge1xuICAgICAgICAgICAgb3ZlcmxheSEuc3R5bGUuZGlzcGxheSA9ICdub25lJztcbiAgICAgICAgICAgIG9rQnRuIS5yZW1vdmVFdmVudExpc3RlbmVyKCdjbGljaycsIG9uT2spO1xuICAgICAgICAgICAgY2FuY2VsQnRuIS5yZW1vdmVFdmVudExpc3RlbmVyKCdjbGljaycsIG9uQ2FuY2VsKTtcbiAgICAgICAgICAgIHJlc29sdmUocmVzdWx0KTtcbiAgICAgICAgfVxuICAgICAgICBmdW5jdGlvbiBvbk9rKCkgeyBjbGVhbnVwKHRydWUpOyB9XG4gICAgICAgIGZ1bmN0aW9uIG9uQ2FuY2VsKCkgeyBjbGVhbnVwKGZhbHNlKTsgfVxuICAgICAgICBva0J0bi5hZGRFdmVudExpc3RlbmVyKCdjbGljaycsIG9uT2spO1xuICAgICAgICBjYW5jZWxCdG4uYWRkRXZlbnRMaXN0ZW5lcignY2xpY2snLCBvbkNhbmNlbCk7XG4gICAgfSk7XG59O1xuXG59KSgpO1xuIl0sCiAgIm1hcHBpbmdzIjogIjs7Ozs7Ozs7Ozs7O0FBQUE7QUFBQTtBQUtBLE9BQUMsV0FBVztBQUFFO0FBRWQsWUFBSSxLQUFLLFNBQVMsZUFBZSxnQkFBZ0I7QUFDakQsWUFBSSxNQUFNLFNBQVMsZUFBZSxjQUFjO0FBQ2hELFlBQUksU0FBbUIsQ0FBQztBQUV4QixpQkFBUyxhQUFhO0FBQ2xCLGNBQUksQ0FBQyxNQUFNLENBQUMsT0FBTyxPQUFPLFdBQVcsRUFBRztBQUN4QyxhQUFHLE1BQU0sVUFBVTtBQUNuQixjQUFJLGNBQWMsT0FBTyxLQUFLLGFBQWE7QUFBQSxRQUMvQztBQUVBLGVBQU8sVUFBVSxTQUFTLEtBQWMsS0FBYyxNQUFlLEtBQWMsS0FBYztBQUM3RixjQUFJLE9BQVEsT0FBUSxJQUFjLFFBQzVCLE9BQVEsSUFBYyxLQUFLLElBQzFCLE9BQU8sR0FBRyxJQUFJLFNBQVMsT0FBTyxHQUFHLElBQUksTUFBTSxPQUFPLElBQUksSUFBSSxNQUFNLE9BQU8sR0FBRztBQUNqRixpQkFBTyxLQUFLLElBQUk7QUFDaEIscUJBQVc7QUFDWCxpQkFBTztBQUFBLFFBQ1g7QUFFQSxlQUFPLGlCQUFpQixzQkFBc0IsU0FBUyxHQUFHO0FBQ3RELGNBQUksU0FBVSxFQUE0QjtBQUMxQyxjQUFJLE9BQU8seUJBQXlCLFVBQVcsT0FBaUIsUUFBUSxPQUFRLE9BQWlCLEtBQUssSUFBSSxPQUFPLE1BQU07QUFDdkgsaUJBQU8sS0FBSyxJQUFJO0FBQ2hCLHFCQUFXO0FBQUEsUUFDZixDQUFDO0FBRUQsZUFBTyxpQkFBaUIsU0FBUyxTQUFtQztBQUNoRSxpQkFBTyxJQUFJLFFBQVEsU0FBUyxTQUFTO0FBQ2pDLGdCQUFJLFVBQVUsU0FBUyxlQUFlLHdCQUF3QjtBQUM5RCxnQkFBSSxRQUFRLFNBQVMsZUFBZSx3QkFBd0I7QUFDNUQsZ0JBQUksUUFBUSxTQUFTLGVBQWUsbUJBQW1CO0FBQ3ZELGdCQUFJLFlBQVksU0FBUyxlQUFlLHVCQUF1QjtBQUMvRCxnQkFBSSxDQUFDLFdBQVcsQ0FBQyxTQUFTLENBQUMsU0FBUyxDQUFDLFdBQVc7QUFBRSxzQkFBUSxPQUFPLFFBQVEsT0FBTyxDQUFDO0FBQUc7QUFBQSxZQUFRO0FBQzVGLGtCQUFNLGNBQWM7QUFDcEIsb0JBQVEsTUFBTSxVQUFVO0FBQ3hCLGtCQUFNLE1BQU07QUFDWixxQkFBUyxRQUFRLFFBQWlCO0FBQzlCLHNCQUFTLE1BQU0sVUFBVTtBQUN6QixvQkFBTyxvQkFBb0IsU0FBUyxJQUFJO0FBQ3hDLHdCQUFXLG9CQUFvQixTQUFTLFFBQVE7QUFDaEQsc0JBQVEsTUFBTTtBQUFBLFlBQ2xCO0FBQ0EscUJBQVMsT0FBTztBQUFFLHNCQUFRLElBQUk7QUFBQSxZQUFHO0FBQ2pDLHFCQUFTLFdBQVc7QUFBRSxzQkFBUSxLQUFLO0FBQUEsWUFBRztBQUN0QyxrQkFBTSxpQkFBaUIsU0FBUyxJQUFJO0FBQ3BDLHNCQUFVLGlCQUFpQixTQUFTLFFBQVE7QUFBQSxVQUNoRCxDQUFDO0FBQUEsUUFDTDtBQUFBLE1BRUEsR0FBRztBQUFBO0FBQUE7IiwKICAibmFtZXMiOiBbXQp9Cg==

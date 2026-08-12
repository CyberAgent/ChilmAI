(function () {
  var ALLOWED_EXTENSIONS = /\.(csv|xlsx|xls|xlsm|xlsb)$/i;

  function isFileFormatValid(file) {
    return ALLOWED_EXTENSIONS.test(file.name);
  }

  function showFileFormatError(input) {
    var errorEl = document.getElementById(input.name + '-format-error');
    if (!errorEl) {
      return;
    }
    var file = input.files && input.files[0];
    if (!file || isFileFormatValid(file)) {
      errorEl.hidden = true;
      return;
    }
    errorEl.textContent = '「' + file.name + '」はアップロードに対応していません。CSV または Excel（.xlsx / .xls / .xlsm / .xlsb）ファイルを選択してください。';
    errorEl.hidden = false;
  }

  function setMatchEnabled(form, enabled) {
    var matchButton = form.querySelector('[data-action="match"]') || document.querySelector('[data-action="match"]');
    if (!matchButton) {
      return;
    }
    matchButton.disabled = !enabled;
  }

  function setValidateEnabled(form, enabled) {
    var validateButton = form.querySelector('[data-action="validate"]') || document.querySelector('[data-action="validate"]');
    if (!validateButton) {
      return;
    }
    validateButton.disabled = !enabled;
    var hint = document.getElementById('validate-button-hint');
    if (hint) {
      hint.hidden = enabled;
    }
  }

  function allFilesSelected(form) {
    var fileInputs = form.querySelectorAll('input[type="file"][required]');
    return Array.prototype.every.call(fileInputs, function (input) {
      var file = input.files && input.files[0];
      return file && isFileFormatValid(file);
    });
  }

  function resolveAction(form, submitter) {
    if (!submitter) {
      return {
        url: form.getAttribute('hx-post'),
        targetSelector: form.getAttribute('hx-target')
      };
    }

    return {
      url: submitter.getAttribute('data-hx-post') || form.getAttribute('hx-post'),
      targetSelector: submitter.getAttribute('data-hx-target') || form.getAttribute('hx-target')
    };
  }

  async function submitWithHx(form, submitter) {
    var action = resolveAction(form, submitter);
    var url = action.url;
    var targetSelector = action.targetSelector;
    if (!url || !targetSelector) {
      return;
    }

    var target = document.querySelector(targetSelector);
    if (!target) {
      return;
    }

    var isMatchAction = submitter && submitter.getAttribute('data-action') === 'match';
    var isValidateAction = submitter && submitter.getAttribute('data-action') === 'validate';
    var fileChangedDuringMatch = false;
    if (isMatchAction) {
      submitter.disabled = true;
      form.querySelectorAll('input[type="file"]').forEach(function (input) {
        input.addEventListener('change', function onChangeDuringMatch() {
          fileChangedDuringMatch = true;
          input.removeEventListener('change', onChangeDuringMatch);
        });
      });
      target.innerHTML =
        '<div class="matching-loading" aria-live="polite" aria-busy="true">' +
        '<span class="matching-loading__spinner" aria-hidden="true"></span>' +
        '<span>マッチング中...</span>' +
        '</div>';
      document.dispatchEvent(new CustomEvent('chilm:before-match'));
    }
    if (isValidateAction) {
      submitter.disabled = true;
      target.innerHTML =
        '<div class="matching-loading" aria-live="polite" aria-busy="true">' +
        '<span class="matching-loading__spinner" aria-hidden="true"></span>' +
        '<span>データ確認中...</span>' +
        '</div>';
    }

    var formData = new FormData(form);
    var fetchError = null;
    try {
      var response = await fetch(url, {
        method: 'POST',
        body: formData
      });

      target.innerHTML = await response.text();

      if (!isMatchAction && !isValidateAction) {
        var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        target.scrollIntoView({ behavior: prefersReducedMotion ? 'instant' : 'smooth', block: 'start' });
      }

      var resultMode = response.headers.get('X-Result-Mode');

      if (submitter && submitter.getAttribute('data-action') === 'validate') {
        var isValid = response.headers.get('X-Validation-Status') === 'valid';
        setMatchEnabled(form, isValid);
        document.dispatchEvent(new CustomEvent('chilm:after-validate', { detail: { valid: isValid } }));
      }

      if (isMatchAction && (resultMode === 'match' || resultMode === 'validate-error' || resultMode === 'solver-error')) {
        document.dispatchEvent(new CustomEvent('chilm:after-match', { detail: { success: resultMode === 'match' } }));
      }
    } catch (error) {
      fetchError = error;
      throw error;
    } finally {
      if (isMatchAction) {
        if (!fileChangedDuringMatch) {
          submitter.disabled = false;
        }
        if (fetchError) {
          target.innerHTML =
            '<p class="matching-error">通信エラーが発生しました。再度お試しください。</p>';
          document.dispatchEvent(new CustomEvent('chilm:after-match', { detail: { success: false } }));
        }
      }
      if (isValidateAction) {
        submitter.disabled = false;
        if (fetchError) {
          target.innerHTML =
            '<p class="matching-error">通信エラーが発生しました。再度お試しください。</p>';
        }
      }
    }
  }

  function updateFileSummary(input) {
    var summary = document.querySelector('[data-file-summary="' + input.name + '"]');
    var dropArea = input.closest('.dads-file-upload__drop-area');
    if (!summary) {
      return;
    }

    if (!input.files || input.files.length === 0) {
      summary.textContent = 'ファイルが選択されていません';
      summary.removeAttribute('data-selected');
      summary.removeAttribute('data-format-error');
      if (dropArea) {
        dropArea.removeAttribute('data-selected');
        dropArea.removeAttribute('data-format-error');
      }
      return;
    }

    var file = input.files[0];
    var names = Array.prototype.map.call(input.files, function (f) {
      return f.name;
    });

    if (isFileFormatValid(file)) {
      summary.textContent = '選択済み：' + names.join(', ');
      summary.setAttribute('data-selected', '');
      summary.removeAttribute('data-format-error');
      if (dropArea) {
        dropArea.setAttribute('data-selected', '');
        dropArea.removeAttribute('data-format-error');
      }
    } else {
      summary.textContent = names.join(', ');
      summary.removeAttribute('data-selected');
      summary.setAttribute('data-format-error', '');
      if (dropArea) {
        dropArea.removeAttribute('data-selected');
        dropArea.setAttribute('data-format-error', '');
      }
    }
  }

  function downloadExcel(trigger) {
    var selector = trigger.getAttribute('data-download-excel');
    if (!selector) {
      return;
    }
    var source = document.querySelector(selector);
    if (!source) {
      return;
    }

    var b64 = source.textContent.trim();
    var binary = atob(b64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    var blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = trigger.getAttribute('data-download-filename') || 'matching_result.xlsx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 0);
  }

  function registerForms() {
    var forms = document.querySelectorAll('form[hx-post][hx-target]');
    forms.forEach(function (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        submitWithHx(form, event.submitter).catch(function (error) {
          console.error(error);
        });
      });

      var fileInputs = form.querySelectorAll('input[type="file"]');
      fileInputs.forEach(function (input) {
        input.addEventListener('change', function () {
          updateFileSummary(input);
          showFileFormatError(input);
          setMatchEnabled(form, false);
          setValidateEnabled(form, allFilesSelected(form));
        });

        var dropArea = input.closest('.dads-file-upload__drop-area');
        if (!dropArea) {
          return;
        }

        dropArea.addEventListener('dragover', function (event) {
          event.preventDefault();
          dropArea.setAttribute('data-drag-over', '');
        });

        dropArea.addEventListener('dragleave', function (event) {
          if (!dropArea.contains(event.relatedTarget)) {
            dropArea.removeAttribute('data-drag-over');
          }
        });

        dropArea.addEventListener('drop', function (event) {
          event.preventDefault();
          dropArea.removeAttribute('data-drag-over');
          var files = event.dataTransfer && event.dataTransfer.files;
          if (!files || files.length === 0) {
            return;
          }
          var dt = new DataTransfer();
          dt.items.add(files[0]);
          input.files = dt.files;
          input.dispatchEvent(new Event('change', { bubbles: true }));
        });
      });
    });
  }

  document.addEventListener('click', function (event) {
    var excelTrigger = event.target.closest('[data-download-excel]');
    if (excelTrigger) {
      downloadExcel(excelTrigger);
      return;
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', registerForms);
  } else {
    registerForms();
  }
})();

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

  // ファイルや追加の入力項目を変更するたびに進める世代。データ確認の応答が届いたときに
  // 送信時から変わっていれば、変更前の入力の結果なのでマッチングを有効にしない。
  var inputGenerations = new WeakMap();

  function inputGeneration(form) {
    return inputGenerations.get(form) || 0;
  }

  function invalidateInputs(form) {
    inputGenerations.set(form, inputGeneration(form) + 1);
    setMatchEnabled(form, false);
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
    if (isMatchAction) {
      submitter.disabled = true;
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
    var generation = inputGeneration(form);
    // 応答待ちの間に入力が変わったら、変更前の入力の結果は表示せず、画面の状態も更新しない。
    function isStale() {
      return (isMatchAction || isValidateAction) && generation !== inputGeneration(form);
    }
    var fetchError = null;
    try {
      var response = await fetch(url, {
        method: 'POST',
        body: formData
      });
      var html = await response.text();
      if (isStale()) {
        return;
      }

      target.innerHTML = html;

      if (!isMatchAction && !isValidateAction) {
        var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        target.scrollIntoView({ behavior: prefersReducedMotion ? 'instant' : 'smooth', block: 'start' });
      }

      var resultMode = response.headers.get('X-Result-Mode');

      if (isValidateAction) {
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
      if (isValidateAction) {
        submitter.disabled = false;
      }
      if (isStale()) {
        target.innerHTML =
          '<p class="empty-state">入力が変更されたため、もう一度データ確認を実行してください。</p>';
      } else if (isMatchAction || isValidateAction) {
        submitter.disabled = false;
        if (fetchError) {
          target.innerHTML =
            '<p class="matching-error">通信エラーが発生しました。再度お試しください。</p>';
          if (isMatchAction) {
            document.dispatchEvent(new CustomEvent('chilm:after-match', { detail: { success: false } }));
          }
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

      // 追加の入力項目は前処理の結果を変えうるため、変更したらデータ確認からやり直す。
      form.querySelectorAll('[name^="param__"]').forEach(function (input) {
        // 入力中（change が発生する前）に応答が届く場合に備えて input も監視する。
        ['input', 'change'].forEach(function (type) {
          input.addEventListener(type, function () {
            invalidateInputs(form);
          });
        });
      });

      var fileInputs = form.querySelectorAll('input[type="file"]');
      fileInputs.forEach(function (input) {
        input.addEventListener('change', function () {
          updateFileSummary(input);
          showFileFormatError(input);
          invalidateInputs(form);
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

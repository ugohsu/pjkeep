// accounts.js - 勘定科目マスタ

const ELEMENT_LABELS = {
  assets: '資産', liabilities: '負債', equity: '純資産',
  revenues: '収益', expenses: '費用'
};
const ELEMENT_ORDER = ['assets', 'liabilities', 'equity', 'revenues', 'expenses'];

function showAlert(msg, type) {
  $('#alert-box').html(
    `<div class="alert alert-${type} alert-dismissible"><button type="button" class="btn-close" data-bs-dismiss="alert"></button>${msg}</div>`
  );
}
function showModalAlert(msg, type) {
  $('#modal-alert').html(
    `<div class="alert alert-${type} alert-dismissible"><button type="button" class="btn-close" data-bs-dismiss="alert"></button>${msg}</div>`
  );
}

function loadAccounts() {
  $.getJSON('/api/accounts').then(function(data) {
    renderAccounts(data);
  });
}

function renderAccounts(data) {
  // element別に分類
  const groups = {};
  ELEMENT_ORDER.forEach(e => { groups[e] = []; });
  data.forEach(a => { if (groups[a.element]) groups[a.element].push(a); });

  let html = '';
  ELEMENT_ORDER.forEach(function(elem) {
    const accounts = groups[elem];
    const label = ELEMENT_LABELS[elem];
    html += `
      <div class="card mb-3">
        <div class="card-header py-2"><strong>${label}</strong></div>
        <div class="table-responsive">
          <table class="table table-sm table-hover mb-0">
            <thead class="table-light">
              <tr><th>科目名</th><th>コード</th><th style="width:60px">順序</th><th style="width:100px"></th></tr>
            </thead>
            <tbody>`;
    if (accounts.length === 0) {
      html += '<tr><td colspan="4" class="text-muted ps-3">（登録なし）</td></tr>';
    }
    accounts.forEach(function(a) {
      html += `<tr>
        <td>${a.name}</td>
        <td class="font-monospace small text-muted">${a.code}</td>
        <td class="text-center">${a.sort_order}</td>
        <td>
          <button class="btn btn-xs btn-outline-secondary btn-edit me-1"
                  data-id="${a.id}" data-name="${a.name}" data-code="${a.code}"
                  data-element="${a.element}" data-sort="${a.sort_order}">編集</button>
          <button class="btn btn-xs btn-outline-danger btn-del" data-id="${a.id}" data-name="${a.name}">削除</button>
        </td>
      </tr>`;
    });
    html += '</tbody></table></div></div>';
  });
  $('#accounts-list').html(html);
}

// 追加モーダルを開く（新規）
$('[data-bs-target="#modal-account"]').on('click', function() {
  $('#modal-title').text('勘定科目の追加');
  $('#edit-id').val('');
  $('#edit-name').val('');
  $('#edit-code').val('');
  $('#edit-element').val('expenses');
  $('#edit-sort').val('0');
  $('#modal-alert').empty();
});

// 編集ボタン
$(document).on('click', '.btn-edit', function() {
  const btn = $(this);
  $('#modal-title').text('勘定科目の編集');
  $('#edit-id').val(btn.data('id'));
  $('#edit-name').val(btn.data('name'));
  $('#edit-code').val(btn.data('code'));
  $('#edit-element').val(btn.data('element'));
  $('#edit-sort').val(btn.data('sort'));
  $('#modal-alert').empty();
  new bootstrap.Modal('#modal-account').show();
});

// 削除ボタン
$(document).on('click', '.btn-del', function() {
  const id = $(this).data('id');
  const name = $(this).data('name');
  if (!confirm(`「${name}」を削除しますか？\n仕訳が存在する場合は削除できません。`)) return;
  $.ajax({
    url: `/api/accounts/${id}`,
    method: 'DELETE',
    success: function() {
      showAlert('削除しました', 'success');
      loadAccounts();
    },
    error: function(xhr) {
      showAlert(xhr.responseJSON?.error || '削除に失敗しました', 'danger');
    }
  });
});

// 保存ボタン
$('#btn-save').on('click', function() {
  const id = $('#edit-id').val();
  const payload = {
    name: $('#edit-name').val().trim(),
    code: $('#edit-code').val().trim(),
    element: $('#edit-element').val(),
    sort_order: parseInt($('#edit-sort').val(), 10) || 0
  };
  if (!payload.name || !payload.code) {
    showModalAlert('名前とコードは必須です', 'warning');
    return;
  }
  const url = id ? `/api/accounts/${id}` : '/api/accounts';
  const method = id ? 'PUT' : 'POST';
  $.ajax({
    url, method,
    contentType: 'application/json',
    data: JSON.stringify(payload),
    success: function() {
      bootstrap.Modal.getInstance('#modal-account')?.hide();
      showAlert(id ? '更新しました' : '追加しました', 'success');
      loadAccounts();
    },
    error: function(xhr) {
      showModalAlert(xhr.responseJSON?.error || '保存に失敗しました', 'danger');
    }
  });
});

// 名前入力でコードを自動生成（新規のみ）
$('#edit-name').on('input', function() {
  if ($('#edit-id').val()) return; // 編集中は変更しない
  const code = 'acc_' + Date.now().toString(36);
  $('#edit-code').val(code);
});

// ---- COA ダウンロード ----
$('#btn-download-coa').on('click', function () {
  $.getJSON('/api/accounts').then(function (data) {
    const payload = data.map(function (a) {
      return { name: a.name, code: a.code, element: a.element, sort_order: a.sort_order };
    });
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'accounts.json';
    a.click();
    URL.revokeObjectURL(url);
  });
});

// ---- バッチ追加 ----
$('#btn-batch-accounts-save').on('click', function () {
  $('#batch-accounts-result').html('');
  let payload;
  try {
    payload = JSON.parse($('#batch-accounts-input').val());
  } catch (e) {
    $('#batch-accounts-result').html(
      `<div class="alert alert-danger">JSON のパースに失敗しました: ${e.message}</div>`
    );
    return;
  }
  if (!Array.isArray(payload)) {
    $('#batch-accounts-result').html(
      '<div class="alert alert-danger">JSON の形式が不正です（配列にしてください）。</div>'
    );
    return;
  }

  $.ajax({
    url: '/api/accounts/batch',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({ accounts: payload }),
    success: function (res) {
      let html = `<div class="alert alert-success">${res.inserted} 件を追加しました。</div>`;
      if (res.errors && res.errors.length > 0) {
        html += '<ul class="small text-danger mb-0">';
        res.errors.forEach(e => {
          html += `<li>${e.message}</li>`;
        });
        html += '</ul>';
      }
      $('#batch-accounts-result').html(html);
      loadAccounts();
    },
    error: function (xhr) {
      const msg = xhr.responseJSON?.error || xhr.responseText;
      $('#batch-accounts-result').html(
        `<div class="alert alert-danger">エラー: ${msg}</div>`
      );
    }
  });
});

// バッチモーダルを開くときに結果欄をクリア
$('#modal-batch-accounts').on('show.bs.modal', function () {
  $('#batch-accounts-result').html('');
});

$(function() {
  loadAccounts();
});

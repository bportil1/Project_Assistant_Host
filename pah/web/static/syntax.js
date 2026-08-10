(() => {
  const esc = s => s.replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
  const span = (cls, s) => `<span class="${cls}">${esc(s)}</span>`;
  const PY_KEYWORDS = new Set(`False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case`.split(/\s+/));
  const JS_KEYWORDS = new Set(`break case catch class const continue debugger default delete do else export extends finally for function if import in instanceof let new return static super switch this throw try typeof var void while with yield async await of true false null undefined`.split(/\s+/));

  function codeLike(src, language) {
    const kw = language === 'python' ? PY_KEYWORDS : JS_KEYWORDS;
    let out = '', i = 0;
    while (i < src.length) {
      const c = src[i], n = src[i+1] || '';
      if ((language === 'python' && c === '#') || (language !== 'python' && c === '/' && n === '/')) {
        const j = src.indexOf('\n', i);
        const end = j < 0 ? src.length : j;
        out += span('syn-comment', src.slice(i, end)); i = end; continue;
      }
      if (language !== 'python' && c === '/' && n === '*') {
        const j = src.indexOf('*/', i+2); const end = j < 0 ? src.length : j+2;
        out += span('syn-comment', src.slice(i, end)); i = end; continue;
      }
      if (c === '"' || c === "'" || (language !== 'python' && c === '`')) {
        let quote = c, triple = language === 'python' && src.slice(i,i+3) === c.repeat(3);
        let j = i + (triple ? 3 : 1);
        while (j < src.length) {
          if (src[j] === '\\') { j += 2; continue; }
          if (triple ? src.slice(j,j+3) === quote.repeat(3) : src[j] === quote) { j += triple ? 3 : 1; break; }
          j++;
        }
        out += span('syn-string', src.slice(i,j)); i = j; continue;
      }
      if (language === 'python' && c === '@') {
        const m = src.slice(i).match(/^@[A-Za-z_][\w.]*/);
        if (m) { out += span('syn-decorator', m[0]); i += m[0].length; continue; }
      }
      if (/\d/.test(c) && !/[\w]/.test(src[i-1] || '')) {
        const m = src.slice(i).match(/^(?:0[xob][0-9a-f_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:e[+-]?\d[\d_]*)?)/i);
        if (m) { out += span('syn-number', m[0]); i += m[0].length; continue; }
      }
      if (/[A-Za-z_$]/.test(c)) {
        const m = src.slice(i).match(/^[A-Za-z_$][\w$]*/); const word = m[0];
        const cls = kw.has(word) ? 'syn-keyword' : ((/^(def|class|function)$/.test((src.slice(0,i).match(/\b\w+\s*$/)||[''])[0]?.trim())) ? 'syn-name' : '');
        out += cls ? span(cls, word) : esc(word); i += word.length; continue;
      }
      if (/[-+*=!<>/%&|^~?:]/.test(c)) { out += span('syn-operator', c); i++; continue; }
      out += esc(c); i++;
    }
    return out;
  }

  function markdown(src) {
    return src.split('\n').map(line => {
      if (/^\s*```/.test(line)) return span('syn-code', line);
      if (/^\s*#{1,6}\s/.test(line)) return span('syn-heading', line);
      let s = esc(line);
      s = s.replace(/(`[^`]+`)/g, '<span class="syn-code">$1</span>');
      s = s.replace(/(\[[^\]]+\]\([^\)]+\))/g, '<span class="syn-link">$1</span>');
      s = s.replace(/(^|\s)([-*+] |\d+\. )/g, '$1<span class="syn-punct">$2</span>');
      return s;
    }).join('\n');
  }

  function jsonLike(src) {
    let out = esc(src);
    out = out.replace(/(&quot;|\")/g, '$1');
    out = out.replace(/("(?:\\.|[^"\\])*"\s*:)/g, '<span class="syn-name">$1</span>');
    out = out.replace(/("(?:\\.|[^"\\])*")/g, '<span class="syn-string">$1</span>');
    out = out.replace(/\b(true|false|null)\b/g, '<span class="syn-keyword">$1</span>');
    out = out.replace(/\b-?\d+(?:\.\d+)?(?:e[+-]?\d+)?\b/gi, '<span class="syn-number">$&</span>');
    return out;
  }

  function yaml(src) {
    return src.split('\n').map(line => {
      if (/^\s*#/.test(line)) return span('syn-comment', line);
      let s = esc(line);
      s = s.replace(/^(\s*)([\w.-]+)(\s*:)/, '$1<span class="syn-name">$2</span>$3');
      s = s.replace(/(["'][^"']*["'])/g, '<span class="syn-string">$1</span>');
      s = s.replace(/\b(true|false|null|yes|no)\b/gi, '<span class="syn-keyword">$1</span>');
      return s;
    }).join('\n');
  }

  function latex(src) {
    let out = esc(src);
    out = out.replace(/(^|\n)(\s*%[^\n]*)/g, '$1<span class="syn-comment">$2</span>');
    out = out.replace(/(\\[A-Za-z@]+\*?)/g, '<span class="syn-keyword">$1</span>');
    out = out.replace(/([{}\[\]])/g, '<span class="syn-punct">$1</span>');
    return out;
  }

  function markup(src) {
    return esc(src).replace(/(&lt;\/?)([\w:-]+)([^&]*?)(\/?>)/g, (_, a,b,c,d) =>
      `<span class="syn-punct">${a}</span><span class="syn-tag">${b}</span>${c.replace(/([\w:-]+)(=)/g,'<span class="syn-attr">$1</span>$2')}<span class="syn-punct">${d}</span>`
    );
  }

  window.PAHSyntax = {
    highlight(src, language) {
      switch (language) {
        case 'python': return codeLike(src, 'python');
        case 'javascript': return codeLike(src, 'javascript');
        case 'markdown': return markdown(src);
        case 'json': return jsonLike(src);
        case 'yaml': case 'toml': return yaml(src);
        case 'latex': return latex(src);
        case 'markup': return markup(src);
        case 'shell': return codeLike(src, 'javascript');
        default: return esc(src);
      }
    }
  };
})();

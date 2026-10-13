// Keep URL handling independent of the page so CI can verify the launch contract.
export function repositoryUrl(value) {
  let url;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error('Enter a full GitHub URL starting with https://github.com/.');
  }
  if (url.protocol !== 'https:' || url.hostname !== 'github.com' || url.port ||
      url.username || url.password || url.search || url.hash) {
    throw new Error('Use an HTTPS GitHub repository or branch URL without credentials, query parameters or a fragment.');
  }
  const path = url.pathname.replace(/\/$/, '').split('/').slice(1);
  if (path.length < 2 || !/^[\w-]+$/.test(path[0]) || !/^[\w.-]+$/.test(path[1]) ||
      (path.length > 2 && (path[2] !== 'tree' || path.length < 4 || path.slice(3).some(part => !part)))) {
    throw new Error('Use a GitHub repository URL, or its /tree/branch URL.');
  }
  path[1] = path[1].replace(/\.git$/, '');
  if (!path[1] || path[1] === '.' || path[1] === '..') {
    throw new Error('Enter a GitHub repository name.');
  }
  return `https://github.com/${path.join('/')}`;
}

export function launchUrl(value) {
  return `vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=${encodeURIComponent(repositoryUrl(value))}`;
}

export function developerGuideUrl(value) {
  const repo = repositoryUrl(value).split('/');
  const branch = repo.length > 5 ? repo.slice(6).join('/') : 'HEAD';
  return `${repo.slice(0, 5).join('/')}/blob/${branch}/DEVELOP.md`;
}

if (typeof document !== 'undefined') {
  const form = document.querySelector('#start-form');
  const input = document.querySelector('#repository');
  const error = document.querySelector('#error');
  // The documentation can prefill a branch during a rollout; nothing opens automatically.
  input.value = new URL(location.href).searchParams.get('repository') || '';
  form.addEventListener('submit', event => {
    event.preventDefault();
    error.hidden = true;
    try {
      const repo = repositoryUrl(input.value);
      const target = launchUrl(repo);
      document.querySelector('#launch').href = target;
      document.querySelector('#guide').href = developerGuideUrl(repo);
      document.querySelector('#clone-url').textContent = repo;
      document.querySelector('#next').hidden = false;
      location.href = target;
    } catch (exception) {
      error.textContent = exception.message;
      error.hidden = false;
      document.querySelector('#next').hidden = true;
      input.focus();
    }
  });
}

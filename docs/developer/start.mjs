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
  const repo = repositoryUrl(value);
  if (new URL(repo).pathname.split('/').length > 3) {
    throw new Error('For a branch URL, use Dev Containers: Clone Repository in Container Volume... in VS Code and paste the full branch URL.');
  }
  return `vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=${encodeURIComponent(repo)}`;
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
  const updateButton = () => {
    document.querySelector('#open').textContent = input.value.includes('/tree/')
      ? 'Show branch instructions' : 'Open in VS Code';
  };
  input.addEventListener('input', updateButton);
  updateButton();
  form.addEventListener('submit', event => {
    event.preventDefault();
    error.hidden = true;
    try {
      const repo = repositoryUrl(input.value);
      document.querySelector('#guide').href = developerGuideUrl(repo);
      document.querySelector('#clone-url').textContent = repo;
      document.querySelector('#next').hidden = false;
      const branch = new URL(repo).pathname.split('/').length > 3;
      document.querySelector('#launch').hidden = branch;
      if (branch) {
        document.querySelector('#next-title').textContent = 'Open this branch in VS Code';
        document.querySelector('#instructions').textContent = 'Branch URLs work through the VS Code clone command below. The browser launch link only supports repository URLs and would fail with a /tree/branch address. Paste the full branch URL into the command so the selected branch is preserved.';
      } else {
        const target = launchUrl(repo);
        document.querySelector('#launch').href = target;
        document.querySelector('#next-title').textContent = 'Continue in VS Code';
        document.querySelector('#instructions').textContent = 'Allow your browser to open VS Code. Confirm the clone and workspace trust prompts, then wait for the container build and automatic installation. The first installation can take several minutes.';
        location.href = target;
      }
    } catch (exception) {
      error.textContent = exception.message;
      error.hidden = false;
      document.querySelector('#next').hidden = true;
      input.focus();
    }
  });
}

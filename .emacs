;
;; Load path
;;
(add-to-list 'load-path (expand-file-name "~/lisp"))
;;
;;===
;;
;; Newline required at end of file
;;
;;(setq require-final-newline 9)
;;
;; Numbered backups
;;
(setq version-control 't)
(setq delete-old-versions 't)
(setq kept-old-versions 16)
;;
;; Other misc. functions
;;
(defun my-scroll-up-one-line ()
  (interactive)
  (scroll-up 1))
(defun my-scroll-down-one-line ()
  (interactive)
  (scroll-down 1))
(defun insert-date ()
  (interactive)
  (shell-command "date" 1)
  (forward-line)
  (insert "----------------------------"))
(defun itm ()
  "Shortcut for entering indented-text-mode"
  (interactive)
  (indented-text-mode))
(defun my-recenter ()
  (interactive)
  (recenter 2))
(defun trim-trail (a)
  "Delete trailing whitespace everywhere after point"
  (interactive "P")
  (replace-regexp "[ \t]+$" "") )
(defun eatwhite (a)
  "Delete next chunk of whitespace"
  (interactive "P")
  (re-search-forward "[ \t]+" nil t)
  (replace-match "" nil nil))
(defun make-frame-w80h40 (a)
  "Make frame with width 80 and height 40"
  (interactive "P")
  (make-frame '((width . 80) (height . 40))))
(defun skip-to-matching-paren (arg)
  "Skip to matching paren if on paren or insert \\[skip-to-matching-paren]"
  (interactive "p")
  (cond ((looking-at "\\s\(") (forward-list 1) (backward-char 1))
        ((looking-at "\\s\)") (forward-char 1) (backward-list 1))
        (t (self-insert-command (or arg 1)))))
;;
;; buffer move
;;
(autoload 'buf-move-up "buffer-move" nil t)
(autoload 'buf-move-down "buffer-move" nil t)
;;
;; gid
;;
(autoload 'gid "idutils" nil t)
;;
;; git
;;
(defun enter-git-blame-mode ()
  "Enter git blame mode."
  (interactive "p")
  (magit-blame-mode))
(setq magit-auto-revert-mode nil)
;;
;; Rebind some keys
;;
(define-key esc-map "Q" 'fill-individual-paragraphs)
(define-key esc-map "E" 'fill-nonuniform-paragraphs)
(define-key esc-map "F" 'clang-format-region)
(define-key esc-map "%" 'skip-to-matching-paren)
(define-key esc-map "\C-t" 'untabify)
(global-set-key [?\C-]] 'my-recenter)
(global-set-key [C-=] 'my-recenter)
(global-set-key [C-tab] 'delete-trailing-whitespace)
(global-set-key [M-=] 'gid)
(global-set-key [?\M-=] 'gid)
;;
;; Function key setup. Assumes version 19 or later.
;;
(defun apply-my-key-bindings (&optional x)
  "Apply all of my global key bindings"
  (interactive "P")
  (global-set-key [f1] 'text-scale-increase)
  (global-set-key [f2] 'text-scale-decrease)
  (global-set-key [f3] 'apply-my-key-bindings)
  (global-set-key [f5] 'goto-line)
  (global-set-key [f6] 'find-file-other-frame)
  (global-set-key [f7] 'make-frame)
  (global-set-key [f8] 'delete-frame)
  (global-set-key [f9] 'xref-find-references)
  (global-set-key [f10] 'xref-find-definitions)
  (global-set-key [f11] 'revert-buffer)
  (global-set-key [f12] 'eatwhite))
  (global-set-key [M-=] 'gid)
(apply-my-key-bindings)
;;
;; Change esc-tab to indent relative, not tags completion (which
;; I hardly ever use).
;;
(define-key esc-map "\t" 'indent-relative)
;;
;; Bell
;;
(setq visible-bell 1)
;;
;; Add an exit hook that asks for confirmation if there is
;; more than one file buffer.
;;
;; (defun count-non-nils (list)
;;   (if list
;;       (if (car list)
;;           (+ 1 (count-non-nils (cdr list)))
;;         (count-non-nils (cdr list)))
;;     0))
;; ;;
;; (defun number-of-file-buffers ()
;;   (interactive)
;;   (count-non-nils (mapcar (function (lambda (buf) (buffer-file-name buf))) (buffer-list))))
;; ;;
;; (defun simple-prompt-for-exit-function ()
;;     (if (> (number-of-file-buffers) 1)
;;         (yes-or-no-p "REALLY exit emacs? ")
;;       1))
;; ;;
;; (add-hook 'kill-emacs-query-functions 'simple-prompt-for-exit-function)
;;------------------------------------------------------------------------------
;;
(setq show-trailing-whitespace t)
;;(toggle-show-trailing-whitespace-show-ws)
;;(add-hook 'before-save-hook 'delete-trailing-whitespace)
;;
;; Show line numbers
;;
(line-number-mode 1)
;;
;; Disable these-- I hardly every use them
;;
(put 'downcase-region 'disabled nil)
(put 'upcase-region 'disabled nil)
;;
;; No startup message please
;;
(setq inhibit-startup-message t)
;;
;; Get rid of this annoying warning
;;
(defun suppress-undo-discard-warning ()
  "Suppress warnings about discarding undo info (for large files)."
  (interactive "p")
  (add-to-list 'warning-suppress-types '(undo discard-info)))
;;
;; global/gtags setup
;; sudo apt-get install global
;;
;; (cond
;;  ((string-equal system-type "gnu/linux")
;;   (progn
;;     (add-to-list 'load-path "/usr/share/emacs/site-lisp/global")
;;     (require 'gtags)
;;     (defun nm-gtags-hook () (gtags-mode 1))
;;     (add-hook 'c-mode-common-hook 'nm-gtags-hook)
;;     (global-set-key "\M-." 'gtags-find-tag)
;;     (global-set-key "\M-," 'gtags-find-rtag)
;;     (global-set-key "\M-/" 'gtags-find-pattern))))
;;
;; Java setup
;;
(add-hook 'java-mode-hook
          (lambda () (font-lock-set-up-width-warning 100)))
(add-hook 'java-mode-hook (lambda ()
                            (setq c-basic-offset 4
                                  tab-width 4
                                  indent-tabs-mode f)))
;;
;; Project setup (needed for eglot to work ok)
;;
(require 'project)
(defun project-find-go-module (dir)
  (when-let ((root (locate-dominating-file dir "go.mod")))
    (cons 'go-module root)))
(cl-defmethod project-root ((project (head go-module)))
  (cdr project))
(add-hook 'project-find-functions #'project-find-go-module)
;;
;; Turn off flymake mode when in eglot
;;
(add-hook 'eglot-managed-mode-hook (lambda ()
  (remove-hook 'flymake-diagnostic-functions 'eglot-flymake-backend)
  (flymake-eslint-enable)))
;;
;; Go setup
;;
;;(require 'go-mode-autoloads)
(add-hook 'before-save-hook 'gofmt-before-save)
(setq gofmt-command "goimports")
(add-hook 'go-mode-hook (lambda ()
                          (setq-default)
                          (setq tab-width 4
                                standard-indent 2
                                indent-tabs-mode 1)))
;;
;; Emacs server/client setup. For linux, set server name based on
;; DISPAY value, so that we can have separate emacs servers for the
;; main X session and a remote X session via NX. For macos, we need a
;; slightly different socket name setup.
;;
(cond
 ((string-equal system-type "windows-nt")
  (progn
    (message "Does this even work on windows?")))
 ((string-equal system-type "darwin")
  (progn
    (setenv "PATH" (concat (getenv "PATH") ":/Users/thanm/bin:/usr/local/bin"))
    (setq server-socket-dir (format "/tmp/emacs%d" (user-uid)))))
 ((string-equal system-type "gnu/linux")
  (progn
    (setq visible-bell 1)
    (setq server-name (format "server%s" (getenv "DISPLAY"))))))
;;
(defun ss ()
  (interactive)
  (server-start))
;;
;; The following code written by Austin. See
;; https://go-review.googlesource.com/c/proposal/+/67930
;; ........................................................................
;; This makes fill-paragraph (M-q) add line breaks at sentence
;; boundaries in addition to normal wrapping. This is the style for Go
;; proposals.
;;
;; Loading this script automatically enables this for markdown-mode
;; buffers in the go-design/proposal directory. It can also be
;; manually enabled with M-x enable-fill-split-sentences.
(defun fill-split-sentences (&optional justify)
  "Fill paragraph at point, breaking lines at sentence boundaries."
  (interactive)
  (save-excursion
    ;; Do a trial fill and get the fill prefix for this paragraph.
    (let ((prefix (or (fill-paragraph) ""))
          (end (progn (fill-forward-paragraph 1) (point)))
          (beg (progn (fill-forward-paragraph -1) (point))))
      (save-restriction
        (narrow-to-region (line-beginning-position) end)
        ;; Unfill the paragraph.
        (let ((fill-column (point-max)))
          (fill-region beg end))
        ;; Fill each sentence.
        (goto-char (point-min))
        (while (not (eobp))
          (if (bobp)
              ;; Skip over initial prefix.
              (goto-char beg)
            (delete-horizontal-space 'backward-only)
            (insert "\n" prefix))
          (let ((sbeg (point))
                (fill-prefix prefix))
            (forward-sentence)
            (fill-region-as-paragraph sbeg (point)))))
      prefix)))

(defun enable-fill-split-sentences ()
  "Make fill break lines at sentence boundaries in this buffer."
  (interactive)
  (setq-local fill-paragraph-function #'fill-split-sentences))

;;
;; See https://github.com/jwiegley/use-package
;; and https://github.com/golang/tools/blob/master/gopls/doc/emacs.md
;;
;;(use-package lsp-mode
;;  :ensure t
;;  :commands (lsp lsp-deferred)
;;  :hook (go-mode . lsp-deferred))

;; Set up before-save hooks to format buffer and add/delete imports.
;; Make sure you don't have other gofmt/goimports hooks enabled.
(defun lsp-go-install-save-hooks ()
  (lsp-ui-doc-mode nil)
  (add-hook 'before-save-hook #'lsp-format-buffer t t)
  (add-hook 'before-save-hook #'lsp-organize-imports t t))
(add-hook 'go-mode-hook #'lsp-go-install-save-hooks)

;; Optional - provides fancier overlays.
;;(use-package lsp-ui
;;  :ensure t
;;  :commands lsp-ui-mode)

;; Company mode is a standard completion package that works well with lsp-mode.
;; (use-package company
;;   :ensure t
;;   :config
;;   ;; Optionally enable completion-as-you-type behavior.
;;   (setq company-idle-delay 0)
;;   (setq company-minimum-prefix-length 1))

(require 'company)
;;(require 'yasnippet)

(require 'go-mode)
(require 'eglot)
(add-hook 'go-mode-hook 'eglot-ensure)

;; Disable flymake
(add-hook 'eglot--managed-mode-hook (lambda () (flymake-mode -1)))

;; Optional: install eglot-format-buffer as a save hook.
;; The depth of -10 places this before eglot's willSave notification,
;; so that that notification reports the actual contents that will be saved.
(defun eglot-format-buffer-before-save ()
  (add-hook 'before-save-hook #'eglot-format-buffer -10 t))
(add-hook 'go-mode-hook #'eglot-format-buffer-before-save)

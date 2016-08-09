;;
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
(defun skip-to-matching-paren (arg)
  "Skip to matching paren if on paren or insert \\[skip-to-matching-paren]"
  (interactive "p")
  (cond ((looking-at "\\s\(") (forward-list 1) (backward-char 1))
        ((looking-at "\\s\)") (forward-char 1) (backward-list 1))
        (t (self-insert-command (or arg 1)))))
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
;;(setq sun-esc-bracket t)
;;
;; Key setup. Assumes version 19 or later.
;;
(global-set-key [f1] 'text-scale-increase)
(global-set-key [f2] 'text-scale-decrease)
(global-set-key [f3] 'apply-my-key-bindings)
(global-set-key [f5] 'goto-line)
(global-set-key [f6] 'find-file-other-frame)
(global-set-key [f7] 'make-frame)
(global-set-key [f8] 'delete-frame)
(global-set-key [f9] 'what-line)
(global-set-key [f11] 'revert-buffer)
(global-set-key [f12] 'eatwhite)
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
;; global/gtags setup
;; sudo apt-get install global
;;
(setq inhibit-startup-message t)
;;
(cond
 ((string-equal system-type "gnu/linux")
  (progn
    (add-to-list 'load-path "/usr/share/emacs/site-lisp/global")
    (require 'gtags)
    (defun nm-gtags-hook () (gtags-mode 1))
    (add-hook 'c-mode-common-hook 'nm-gtags-hook)
    (global-set-key "\M-." 'gtags-find-tag)
    (global-set-key "\M-," 'gtags-find-rtag)
    (global-set-key "\M-/" 'gtags-find-pattern))))
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
;; Go setup
;;
(add-hook 'go-mode-hook (lambda ()
                          (setq-default)
                          (load "go-guru")
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
    (setenv "PATH" (concat (getenv "PATH") ":/Users/thanm/bin"))    
    (setq server-socket-dir (format "/tmp/emacs%d" (user-uid)))))
 ((string-equal system-type "gnu/linux")
  (progn
    (setq server-name (format "server%s" (getenv "DISPLAY"))))))
;;
(defun ss ()
  (interactive)
  (server-start))

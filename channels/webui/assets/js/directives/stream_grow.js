function streamGrow(el) {
    let max = 0
    let raf = null
    let ro = null

    const isReleased = () => el.classList.contains('stream-grow-released')
    const hasGrowContent = () => !!el.querySelector('.agent-chain-body, .live-answer')
    const eligible = () => Alpine.store('stream').state !== 'idle' && hasGrowContent() && !isReleased()

    const setMin = (value) => {
        Alpine.mutateDom(() => {
            el.style.minHeight = value
        })
    }

    // measured via the children: the element's own offsetHeight includes the
    // min-height we set, which would hide any shrinkage from us
    const naturalHeight = () => {
        let h = 0
        for (const child of el.children) {
            h += child.offsetHeight
        }
        return h
    }

    const apply = () => {
        if (!eligible()) {
            max = 0
            setMin('')
            return
        }

        // The live shell is the stable surface: it contains both the process
        // chain and the provisional answer. Do not release the pin when a
        // provisional answer appears/retracts; otherwise repeated provisional
        // content causes layout jumps.
        const height = naturalHeight()
        if (height > max) {
            max = height
        }

        if (max > 0 && el.clientHeight < max) {
            setMin(max + 'px')
        }
    }

    const schedule = () => {
        if (raf !== null) return
        raf = requestAnimationFrame(() => {
            raf = null
            const before = growTargets()
            apply()
            if (!sameTargets(before, growTargets())) observeContent()
        })
    }

    const growTargets = () => Array.from(el.querySelectorAll('.agent-chain, .agent-chain-body, .live-answer'))

    const sameTargets = (a, b) => a.length === b.length && a.every((x, i) => x === b[i])

    const observeContent = () => {
        ro?.disconnect()
        ro = null
        if (typeof ResizeObserver === 'undefined') return
        ro = new ResizeObserver(schedule)
        ro.observe(el)
        for (const target of growTargets()) ro.observe(target)
    }

    const isTrackedNode = (node) => {
        return node.nodeType === 1 && (
            node.classList.contains('agent-chain') ||
            node.classList.contains('agent-chain-body') ||
            node.classList.contains('live-answer') ||
            node.closest('.agent-chain, .live-answer')
        )
    }

    const mo = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type !== 'childList') continue

            if (mutation.target.nodeType === 1 && mutation.target.closest('.agent-chain, .live-answer')) {
                schedule()
                return
            }

            for (const node of mutation.addedNodes) {
                if (isTrackedNode(node)) {
                    schedule()
                    return
                }
            }

            for (const node of mutation.removedNodes) {
                if (isTrackedNode(node)) {
                    schedule()
                    return
                }
            }
        }
    })

    mo.observe(el, { childList: true, characterData: true, subtree: true })

    observeContent()

    const stop = Alpine.effect(() => {
        const state = Alpine.store('stream').state
        if (state === 'message_sending') el.classList.remove('stream-grow-released')
        schedule()
    })

    apply()

    return () => {
        mo.disconnect()
        ro?.disconnect()
        stop()
        if (raf !== null) cancelAnimationFrame(raf)
        el.style.minHeight = ''
    }
}

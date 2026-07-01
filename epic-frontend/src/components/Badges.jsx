import React from 'react'
export const Status = ({ value }) => <span className={`badge s-${value}`}>{value.replace('_', ' ')}</span>
export const Priority = ({ value }) => <span className={`badge p-${value}`}>{value}</span>
